"""Compita - Voice agent using OpenAI Realtime API.

Compita is the voice assistant for Reachy Mini Pomodoro.
Supports two audio modes:
1. Browser mode: Audio via WebSocket from dashboard
2. Robot mode: Audio via robot.media (GStreamer)

Wake word detection:
- Listens for "Compita" to activate
- Conversation times out after silence, returns to listening

Audio-driven head movements:
- Uses HeadWobbler to analyze audio output
- Generates realistic head sway/wobble synchronized with speech
"""

import asyncio
import base64
import json
import logging
import os
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

import numpy as np
from scipy.signal import resample

from reachy_mini_pomodoro.voice.tools import PomodoroToolHandler, get_pomodoro_tools

if TYPE_CHECKING:
    from reachy_mini_pomodoro.movements import MovementManager
    from reachy_mini_pomodoro.pomodoro_timer import PomodoroTimer
    from reachy_mini_pomodoro.task_manager import TaskManager
    from reachy_mini_pomodoro.voice.head_wobbler import HeadWobbler

logger = logging.getLogger(__name__)

OPENAI_SAMPLE_RATE = 24000
WAKE_WORD_SAMPLE_RATE = 16000
CONVERSATION_TIMEOUT = 10.0  # seconds of silence before returning to listening


class SessionState(Enum):
    """State of the voice session."""
    LISTENING = "listening"  # Waiting for wake word
    ACTIVE = "active"  # In conversation with user
    PROCESSING = "processing"  # Processing response

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

    Audio I/O is handled externally - this class manages the OpenAI connection,
    tool execution, and animations.
    """

    def __init__(
        self,
        timer: "PomodoroTimer",
        task_manager: "TaskManager",
        movement_manager: Optional["MovementManager"] = None,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "coral",
        on_audio_output: Optional[Callable[[bytes], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,
        head_wobbler: Optional["HeadWobbler"] = None,
    ) -> None:
        """Initialize Compita voice agent.

        Args:
            timer: The Pomodoro timer instance.
            task_manager: The task manager instance.
            movement_manager: Optional movement manager for robot animations.
            openai_api_key: OpenAI API key.
            model: OpenAI model to use.
            voice: Voice to use for responses.
            on_audio_output: Callback for audio output (PCM16 bytes at 24kHz).
            on_transcript: Callback for transcripts (role, text).
            head_wobbler: Optional head wobbler for audio-driven head movements.
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
        self.tool_handler = PomodoroToolHandler(timer, task_manager, movement_manager)

        self.on_audio_output = on_audio_output
        self.on_transcript = on_transcript
        self.head_wobbler = head_wobbler

        self._connection: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self) -> None:
        """Start the voice agent in a background thread."""
        if self._running:
            return

        def run_agent():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.connect())
            except Exception as e:
                logger.error(f"Agent error: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=run_agent, daemon=True)
        self._thread.start()
        logger.info("Compita voice agent thread started")

    async def connect(self) -> None:
        """Connect to OpenAI Realtime API."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("OpenAI SDK not installed. Run: pip install openai")
            return

        client = AsyncOpenAI(api_key=self.api_key)

        logger.info("Connecting to OpenAI Realtime API...")

        async with client.beta.realtime.connect(model=self.model) as conn:
            self._connection = conn
            self._running = True
            logger.info("Connected to OpenAI Realtime API")

            # Configure the session
            await conn.session.update(
                session={
                    "instructions": COMPITA_INSTRUCTIONS,
                    "voice": self.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                    },
                    "tools": get_pomodoro_tools(),
                    "tool_choice": "auto",
                }
            )

            logger.info("Session configured, ready for audio")

            # Process events
            async for event in conn:
                if not self._running:
                    break
                await self._handle_event(event)

        self._connection = None
        self._running = False

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio data to OpenAI.

        Args:
            audio_bytes: PCM16 audio at 24kHz, mono.
        """
        if not self._connection:
            return

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        await self._connection.input_audio_buffer.append(audio=audio_b64)

    async def send_audio_array(self, audio: np.ndarray, sample_rate: int) -> None:
        """Send audio numpy array to OpenAI.

        Args:
            audio: Audio samples (float32 or int16).
            sample_rate: Sample rate of the audio.
        """
        if not self._connection:
            return

        # Convert to int16 if needed
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            audio = (audio * 32767).astype(np.int16)
        elif audio.dtype != np.int16:
            audio = audio.astype(np.int16)

        # Resample to 24kHz if needed
        if sample_rate != OPENAI_SAMPLE_RATE:
            target_len = int(len(audio) * OPENAI_SAMPLE_RATE / sample_rate)
            audio = resample(audio.astype(np.float32), target_len).astype(np.int16)

        await self.send_audio(audio.tobytes())

    async def _handle_event(self, event: Any) -> None:
        """Handle an event from the OpenAI Realtime connection."""
        event_type = event.type

        if event_type == "session.created":
            logger.debug("Session created")

        elif event_type == "session.updated":
            logger.debug("Session updated")

        elif event_type == "input_audio_buffer.speech_started":
            logger.debug("User started speaking")
            self._trigger_animation("listening")
            # Reset head wobbler when user starts speaking
            if self.head_wobbler:
                self.head_wobbler.reset()
            if self.movement_manager:
                self.movement_manager.set_listening(True)

        elif event_type == "input_audio_buffer.speech_stopped":
            logger.debug("User stopped speaking")
            if self.movement_manager:
                self.movement_manager.set_listening(False)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = getattr(event, "transcript", "")
            if transcript and transcript.strip():
                logger.info(f"User: {transcript}")
                if self.on_transcript:
                    self.on_transcript("user", transcript)

        elif event_type == "response.audio_transcript.done":
            transcript = getattr(event, "transcript", "")
            if transcript and transcript.strip():
                logger.info(f"Compita: {transcript}")
                if self.on_transcript:
                    self.on_transcript("assistant", transcript)

        elif event_type == "response.audio.delta":
            delta = getattr(event, "delta", "")
            if delta:
                if self.head_wobbler:
                    self.head_wobbler.feed(delta)  
                if self.on_audio_output:
                    audio_bytes = base64.b64decode(delta)
                    self.on_audio_output(audio_bytes)

        elif event_type == "response.done":
            logger.debug("Response complete")
            self._trigger_animation("idle")

        elif event_type == "response.function_call_arguments.done":
            await self._handle_tool_call(event)

        elif event_type == "error":
            error = getattr(event, "error", {})
            logger.error(f"API error: {error}")

    async def inject_event(self, event_text: str) -> None:
        """Inject a system event into the conversation.

        This triggers the assistant to respond to an event that happened
        outside of the voice conversation (e.g., task completed via web UI).

        Args:
            event_text: Description of the event for the assistant to acknowledge.
        """
        if not self._connection:
            return

        try:
            # Add a system message about the event
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": f"[System event: {event_text}]"}],
                }
            )
            # Trigger a response
            await self._connection.response.create()
            logger.info(f"Injected event: {event_text}")
        except Exception as e:
            logger.error(f"Failed to inject event: {e}")

    async def _handle_tool_call(self, event: Any) -> None:
        """Handle a tool call from the LLM."""
        tool_name = getattr(event, "name", "")
        args_str = getattr(event, "arguments", "{}")
        call_id = getattr(event, "call_id", "")

        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            arguments = {}

        logger.info(f"Tool call: {tool_name}")
        result = await self.tool_handler.dispatch(tool_name, arguments)

        # Trigger animation based on tool
        self._trigger_tool_animation(tool_name, result)

        # Send result back
        if self._connection and call_id:
            await self._connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result),
                }
            )
            await self._connection.response.create()

    def _trigger_animation(self, animation_type: str) -> None:
        """Trigger robot animation."""
        if not self.movement_manager:
            return

        try:
            from reachy_mini_pomodoro.movements import MovementType

            # Don't interrupt important animations (celebration, demos)
            current = self.movement_manager.get_current_movement_type()
            protected_movements = {
                MovementType.CELEBRATION,
                MovementType.TASK_COMPLETE,
                MovementType.BREATHING_DEMO,
                MovementType.STRETCH_DEMO,
                MovementType.FOCUS_COMPLETE,
            }
            if current in protected_movements:
                return

            animations = {
                "listening": MovementType.LISTENING,
                "speaking": MovementType.TALKING,
                "idle": MovementType.IDLE,
            }

            movement = animations.get(animation_type)
            if movement:
                duration = 1.0 if animation_type != "speaking" else 10.0
                self.movement_manager.start_movement(movement, duration=duration, loop=True)

        except Exception:
            pass

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

            # Check if an important animation is already running (from tool handler)
            current = self.movement_manager.get_current_movement_type()
            protected_movements = {
                MovementType.CELEBRATION,
                MovementType.TASK_COMPLETE,
                MovementType.BREATHING_DEMO,
                MovementType.STRETCH_DEMO,
            }
            if current in protected_movements:
                return

            if tool_name == "start_focus":
                self.movement_manager.start_movement(MovementType.FOCUS_START, duration=2.0)
            elif tool_name == "start_break":
                self.movement_manager.start_movement(MovementType.BREAK_START, duration=2.0)
            elif tool_name == "complete_current_task":
                self.movement_manager.start_movement(MovementType.CELEBRATION, duration=3.0)
            elif tool_name == "create_task":
                self.movement_manager.start_movement(MovementType.NOD_YES, duration=1.0)

        except Exception:
            pass

    def stop(self) -> None:
        """Stop the voice agent."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def is_running(self) -> bool:
        """Check if the voice agent is running."""
        return self._running


class CompitaVoiceSession:
    """Manages voice session with wake word detection.

    Like Alexa - listens for "Compita", activates conversation,
    then returns to listening after timeout.

    Includes audio-driven head movements via HeadWobbler for realistic
    talking animation synchronized with speech output.
    """

    def __init__(
        self,
        timer: "PomodoroTimer",
        task_manager: "TaskManager",
        movement_manager: Optional["MovementManager"] = None,
        openai_api_key: Optional[str] = None,
        model: str = "gpt-4o-realtime-preview",
        voice: str = "coral",
        on_audio_output: Optional[Callable[[bytes], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_state_change: Optional[Callable[[SessionState], None]] = None,
    ) -> None:
        """Initialize voice session.

        Args:
            timer: The Pomodoro timer instance.
            task_manager: The task manager instance.
            movement_manager: Optional movement manager for robot animations.
            openai_api_key: OpenAI API key.
            model: OpenAI model to use.
            voice: Voice to use for responses.
            on_audio_output: Callback for audio output (PCM16 bytes at 24kHz).
            on_transcript: Callback for transcripts (role, text).
            on_state_change: Callback when session state changes.
        """
        self.timer = timer
        self.task_manager = task_manager
        self.movement_manager = movement_manager
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.voice = voice

        self.on_audio_output = on_audio_output
        self.on_transcript = on_transcript
        self.on_state_change = on_state_change

        self._state = SessionState.LISTENING
        self._agent: Optional[CompitaVoiceAgent] = None
        self._running = False
        self._last_activity = 0.0
        self._audio_buffer: list[bytes] = []

        # Head wobbler for audio-driven head movements
        self._head_wobbler: Optional["HeadWobbler"] = None
        self._init_head_wobbler()

    def _init_head_wobbler(self) -> None:
        """Initialize the head wobbler for audio-driven head movements."""
        if not self.movement_manager:
            return

        try:
            from reachy_mini_pomodoro.voice.head_wobbler import HeadWobbler

            self._head_wobbler = HeadWobbler(
                set_speech_offsets=self.movement_manager.set_speech_offsets
            )
            self._head_wobbler.start()
            logger.info("Head wobbler initialized for audio-driven movements")
        except ImportError as e:
            logger.debug(f"Head wobbler not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize head wobbler: {e}")

    @property
    def state(self) -> SessionState:
        """Get current session state."""
        return self._state

    def _set_state(self, state: SessionState) -> None:
        """Set session state and notify callback."""
        if self._state != state:
            self._state = state
            logger.info(f"Session state: {state.value}")
            if self.on_state_change:
                self.on_state_change(state)

    async def process_audio(self, audio_bytes: bytes) -> None:
        """Process incoming audio.

        In LISTENING state: Check for wake word in transcript
        In ACTIVE state: Forward to OpenAI agent

        Args:
            audio_bytes: PCM16 audio data.
        """
        if not self._running:
            return

        if self._state == SessionState.LISTENING:
            # Buffer audio for potential wake word
            self._audio_buffer.append(audio_bytes)
            # Keep only last 2 seconds of audio (24000 * 2 * 2 bytes)
            max_buffer_size = OPENAI_SAMPLE_RATE * 2 * 2
            total_size = sum(len(b) for b in self._audio_buffer)
            while total_size > max_buffer_size and self._audio_buffer:
                removed = self._audio_buffer.pop(0)
                total_size -= len(removed)

        elif self._state == SessionState.ACTIVE and self._agent:
            await self._agent.send_audio(audio_bytes)
            self._last_activity = time.time()

    async def _activate_conversation(self) -> None:
        """Activate conversation mode - connect to OpenAI."""
        if self._agent and self._agent.is_running():
            return

        logger.info("Activating conversation...")
        self._set_state(SessionState.ACTIVE)
        self._last_activity = time.time()

        self._agent = CompitaVoiceAgent(
            timer=self.timer,
            task_manager=self.task_manager,
            movement_manager=self.movement_manager,
            openai_api_key=self.openai_api_key,
            model=self.model,
            voice=self.voice,
            on_audio_output=self.on_audio_output,
            on_transcript=self._handle_transcript,
            head_wobbler=self._head_wobbler,
        )

        buffered_audio = b"".join(self._audio_buffer)
        self._audio_buffer.clear()

        async def run_agent():
            try:
                if buffered_audio:
                    asyncio.create_task(self._send_buffered_audio(buffered_audio))
                await self._agent.connect()
            except Exception as e:
                logger.error(f"Failed to connect agent: {e}")
            finally:
                self._deactivate_conversation()

        asyncio.create_task(run_agent())

    async def _send_buffered_audio(self, audio: bytes) -> None:
        """Send buffered audio once agent is connected."""
        for _ in range(50):  
            if self._agent and self._agent._connection:
                await self._agent.send_audio(audio)
                logger.debug(f"Sent {len(audio)} bytes of buffered audio")
                return
            await asyncio.sleep(0.1)

    def _deactivate_conversation(self) -> None:
        """Return to listening mode."""
        if self._agent:
            self._agent.stop()
            self._agent = None

        if self._head_wobbler:
            self._head_wobbler.reset()
        if self.movement_manager:
            self.movement_manager.clear_speech_offsets()

        self._set_state(SessionState.LISTENING)
        self._audio_buffer.clear()
        logger.info("Returned to listening mode")

    def _handle_transcript(self, role: str, text: str) -> None:
        """Handle transcript from agent."""
        self._last_activity = time.time()

        if self.on_transcript:
            self.on_transcript(role, text)

        if role == "user" and "compita" in text.lower():
            self._last_activity = time.time()

    def check_wake_word(self, text: str) -> bool:
        """Check if text contains wake word.

        Args:
            text: Transcript text to check.

        Returns:
            True if wake word detected.
        """
        wake_words = [
            "compita", "compíta", "kompita",
            "computer", "compit", "computa",
            "comply to", "compete", "compito",
            "copita"
        ]
        text_lower = text.lower()
        return any(word in text_lower for word in wake_words)

    async def handle_user_transcript(self, text: str) -> None:
        """Handle user transcript for wake word detection.

        Call this when you have transcript from speech recognition.

        Args:
            text: User's transcribed speech.
        """
        if self._state == SessionState.LISTENING:
            if self.check_wake_word(text):
                logger.info(f"Wake word detected in: {text}")
                await self._activate_conversation()

    async def run_timeout_checker(self) -> None:
        """Check for conversation timeout and return to listening."""
        while self._running:
            await asyncio.sleep(1.0)

            if self._state == SessionState.ACTIVE:
                elapsed = time.time() - self._last_activity
                if elapsed > CONVERSATION_TIMEOUT:
                    logger.info(f"Conversation timeout ({elapsed:.1f}s)")
                    self._deactivate_conversation()

    def start(self) -> None:
        """Start the voice session."""
        self._running = True
        self._set_state(SessionState.LISTENING)
        self._last_activity = time.time()
        logger.info("Voice session started - listening for 'Compita'")

    def stop(self) -> None:
        """Stop the voice session."""
        self._running = False
        if self._agent:
            self._agent.stop()
            self._agent = None

        if self._head_wobbler:
            self._head_wobbler.stop()
            self._head_wobbler = None
        if self.movement_manager:
            self.movement_manager.clear_speech_offsets()

        self._set_state(SessionState.LISTENING)

    def is_running(self) -> bool:
        """Check if session is running."""
        return self._running

    async def activate(self) -> None:
        """Manually activate conversation (e.g., from button press)."""
        if self._state == SessionState.LISTENING:
            await self._activate_conversation()

    async def notify_event(self, event_text: str) -> None:
        """Notify the session about an external event.

        If the session is active, injects the event into the conversation.
        If listening, activates the conversation first.

        Args:
            event_text: Description of the event.
        """
        if self._state == SessionState.LISTENING:
            await self._activate_conversation()
            for _ in range(30):
                if self._agent and self._agent._connection:
                    break
                await asyncio.sleep(0.1)

        if self._agent and self._agent._connection:
            await self._agent.inject_event(event_text)
            self._last_activity = time.time()
