"""Compita - Voice agent using OpenAI Realtime API.

Compita is the voice assistant for Reachy Mini Pomodoro.
Say "Compita" to wake it up and ask about your timer, tasks, or stats.
"""

import asyncio
import json
import logging
import os
import threading
from typing import Any, Optional, TYPE_CHECKING

import websockets

from reachy_mini_pomodoro.voice.tools import PomodoroToolHandler, get_pomodoro_tools

if TYPE_CHECKING:
    from reachy_mini_pomodoro.movements import MovementManager
    from reachy_mini_pomodoro.pomodoro_timer import PomodoroTimer
    from reachy_mini_pomodoro.task_manager import TaskManager

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24000  # OpenAI Realtime API uses 24kHz

COMPITA_INSTRUCTIONS = """You are Compita, a friendly and encouraging productivity assistant for the Reachy Mini Pomodoro app.

Your personality:
- Warm, supportive, and enthusiastic about helping users stay productive
- Concise - keep responses to 1-2 sentences since users are listening
- Encouraging without being overwhelming
- You speak with a slight playful energy

You help users:
- Check their timer status and time remaining
- Start, pause, resume, and stop focus sessions
- Start breaks after completing pomodoros
- Create and manage tasks
- Track their productivity stats

When users say "Compita", acknowledge them warmly and ask how you can help.
When they ask about time remaining, be specific with minutes and seconds.
Celebrate their progress and completed tasks!

Always use the available tools to get accurate information rather than guessing.
"""


class CompitaVoiceAgent:
    """Compita voice agent using OpenAI Realtime API.

    Provides voice-activated control of the Pomodoro app.
    """

    def __init__(
        self,
        timer: "PomodoroTimer",
        task_manager: "TaskManager",
        movement_manager: Optional["MovementManager"] = None,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "coral",
    ) -> None:
        """Initialize Compita voice agent.

        Args:
            timer: The Pomodoro timer instance.
            task_manager: The task manager instance.
            movement_manager: Optional movement manager for robot animations.
            openai_api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
            model: OpenAI model to use.
            voice: Voice to use for responses.
        """
        self.timer = timer
        self.task_manager = task_manager
        self.movement_manager = movement_manager

        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass openai_api_key parameter."
            )

        self.model = model
        self.voice = voice
        self.tool_handler = PomodoroToolHandler(timer, task_manager)

        self._ws: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self) -> None:
        """Start the voice agent in a background thread."""
        if self._running:
            logger.warning("Compita is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()
        logger.info("Compita voice agent started")

    def _run_async_loop(self) -> None:
        """Run the async event loop in a thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._run_session())
        except Exception as e:
            logger.error(f"Compita session error: {e}")
        finally:
            self._loop.close()
            self._running = False

    async def _run_session(self) -> None:
        """Run the OpenAI Realtime session via WebSocket."""
        self._running = True

        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                self._ws = ws

                # Configure the session
                session_config = {
                    "type": "session.update",
                    "session": {
                        "instructions": COMPITA_INSTRUCTIONS,
                        "voice": self.voice,
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.5,
                            "prefix_padding_ms": 300,
                            "silence_duration_ms": 500,
                        },
                        "tools": get_pomodoro_tools(),
                        "tool_choice": "auto",
                    }
                }
                await ws.send(json.dumps(session_config))

                logger.info("Compita connected to OpenAI Realtime API")

                # Process events from the connection
                async for message in ws:
                    if self._stop_event.is_set():
                        break

                    try:
                        event = json.loads(message)
                        await self._handle_event(event)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse event: {message[:100]}")

        except Exception as e:
            logger.error(f"Compita connection error: {e}")
        finally:
            self._ws = None

    async def _handle_event(self, event: dict) -> None:
        """Handle an event from the OpenAI Realtime connection."""
        event_type = event.get("type", "")

        if event_type == "session.created":
            logger.debug("Session created")

        elif event_type == "session.updated":
            logger.debug("Session configured successfully")

        elif event_type == "input_audio_buffer.speech_started":
            logger.debug("User started speaking")
            self._trigger_animation("listening")

        elif event_type == "input_audio_buffer.speech_stopped":
            logger.debug("User stopped speaking")

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "")
            logger.info(f"User said: {transcript}")

        elif event_type == "response.audio_transcript.done":
            transcript = event.get("transcript", "")
            logger.info(f"Compita said: {transcript}")

        elif event_type == "response.audio.delta":
            # Audio is being played - robot could animate
            self._trigger_animation("speaking")

        elif event_type == "response.done":
            logger.debug("Response complete")
            self._trigger_animation("idle")

        elif event_type == "response.function_call_arguments.done":
            await self._handle_tool_call(event)

        elif event_type == "error":
            error = event.get("error", {})
            logger.error(f"Realtime error: {error}")

    async def _handle_tool_call(self, event: dict) -> None:
        """Handle a tool call from the LLM."""
        tool_name = event.get("name", "")
        args_str = event.get("arguments", "{}")
        call_id = event.get("call_id", "")

        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            arguments = {}

        logger.info(f"Tool call: {tool_name}({arguments})")

        # Execute the tool
        result = await self.tool_handler.dispatch(tool_name, arguments)
        logger.debug(f"Tool result: {result}")

        # Trigger animation based on tool
        self._trigger_tool_animation(tool_name, result)

        # Send result back to the connection
        if self._ws and call_id:
            response = {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            }
            await self._ws.send(json.dumps(response))

            # Request a spoken response
            await self._ws.send(json.dumps({"type": "response.create"}))

    def _trigger_animation(self, animation_type: str) -> None:
        """Trigger robot animation."""
        if not self.movement_manager:
            return

        try:
            from reachy_mini_pomodoro.movements import MovementType

            animations = {
                "listening": MovementType.NOD_YES,
                "speaking": MovementType.BREATHING,
                "idle": MovementType.IDLE,
            }

            movement = animations.get(animation_type)
            if movement:
                duration = 1.0 if animation_type != "speaking" else 5.0
                self.movement_manager.start_movement(movement, duration=duration)

        except Exception as e:
            logger.debug(f"Animation error: {e}")

    def _trigger_tool_animation(self, tool_name: str, result: dict) -> None:
        """Trigger animation based on tool execution."""
        if not self.movement_manager:
            return

        try:
            from reachy_mini_pomodoro.movements import MovementType

            success = result.get("success", True)

            if not success:
                self.movement_manager.start_movement(MovementType.NOD_NO, duration=0.8)
                return

            if tool_name == "start_focus":
                self.movement_manager.start_movement(MovementType.FOCUS_START, duration=2.0)
            elif tool_name == "start_break":
                self.movement_manager.start_movement(MovementType.BREAK_START, duration=2.0)
            elif tool_name in ("create_task", "complete_current_task"):
                self.movement_manager.start_movement(MovementType.NOD_YES, duration=1.0)
            elif "completed" in result.get("message", "").lower():
                self.movement_manager.start_movement(MovementType.CELEBRATION, duration=3.0)

        except Exception as e:
            logger.debug(f"Tool animation error: {e}")

    def stop(self) -> None:
        """Stop the voice agent."""
        logger.info("Stopping Compita voice agent...")
        self._stop_event.set()

        if self._ws:
            # Close connection from the event loop
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._close_connection(), self._loop
                )

        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        self._running = False
        logger.info("Compita voice agent stopped")

    async def _close_connection(self) -> None:
        """Close the realtime connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    def is_running(self) -> bool:
        """Check if the voice agent is running."""
        return self._running
