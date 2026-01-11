"""Main Pomodoro app for Reachy Mini."""

import asyncio
import logging
import threading
import time
import traceback
from typing import List, Optional
from urllib.parse import urlparse

import uvicorn
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from reachy_mini import ReachyMini, ReachyMiniApp

from reachy_mini_pomodoro.config import (
    CONTROL_LOOP_FREQUENCY,
    CUSTOM_APP_URL,
    DEFAULT_COMPITA_SETTINGS,
    TimerState,
    CompitaSettings,
)
from reachy_mini_pomodoro.movements import MovementManager, MovementType
from reachy_mini_pomodoro.pomodoro_timer import PomodoroTimer, TimerEvent
from reachy_mini_pomodoro.task_manager import TaskManager

logger = logging.getLogger(__name__)


class AddTaskRequest(BaseModel):
    title: str
    estimated_pomodoros: int = 1
    notes: str = ""
    tags: Optional[List[str]] = None
    priority: str = "medium"
    due_date: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    estimated_pomodoros: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None


class ReorderTasksRequest(BaseModel):
    task_ids: List[str]


class UpdateSettingsRequest(BaseModel):
    focus_duration: Optional[int] = None
    short_break_duration: Optional[int] = None
    long_break_duration: Optional[int] = None
    pomodoros_until_long_break: Optional[int] = None


class UpdateCompitaSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    openai_api_key: Optional[str] = None
    voice: Optional[str] = None


class ReachyMiniPomodoro(ReachyMiniApp):
    """Pomodoro productivity timer app with Reachy Mini robot companion.

    Media backend is auto-detected by the Dashboard for robot mic support.
    """

    custom_app_url: str | None = CUSTOM_APP_URL
    def __init__(
        self,
        localhost_only: bool = True,
        compita_settings: Optional[CompitaSettings] = None,
        media_backend_override: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.localhost_only = localhost_only
        self._media_backend_override = media_backend_override
        self.logger = logging.getLogger("reachy_mini.pomodoro")
        self.task_manager = TaskManager()
        self.timer = PomodoroTimer()
        self.movement_manager = MovementManager()
        self.timer.add_event_listener(self._handle_timer_event)
        self._sound_enabled = True
        self._compita_settings = compita_settings or DEFAULT_COMPITA_SETTINGS
        self._compita = None
        self._active_voice_session = None  # Track active voice session for notifications
        self._reachy_mini = None  # Store robot reference for audio
        self._robot_voice_loop = None  # Robot microphone voice loop

    def _handle_timer_event(self, event: TimerEvent) -> None:
        self.logger.info(f"Timer event: {event.event_type} - {event.data}")

        if event.event_type == "focus_started":
            self.movement_manager.start_movement(MovementType.FOCUS_START, duration=2.0)
            self.movement_manager.queue_movement(
                MovementType.BREATHING, duration=60.0, loop=True
            )

        elif event.event_type == "focus_reminder":
            self.movement_manager.start_movement(
                MovementType.FOCUS_REMINDER, duration=1.5
            )
            self.movement_manager.queue_movement(
                MovementType.BREATHING, duration=60.0, loop=True
            )

        elif event.event_type == "focus_completed":
            self.movement_manager.start_movement(
                MovementType.FOCUS_COMPLETE, duration=2.0
            )
            task = self.task_manager.complete_pomodoro()
            if task and task.completed_pomodoros >= task.estimated_pomodoros:
                self.movement_manager.queue_movement(
                    MovementType.TASK_COMPLETE, duration=2.0
                )

        elif event.event_type == "break_started":
            self.movement_manager.start_movement(
                MovementType.BREAK_START, duration=2.0
            )
            self.movement_manager.queue_movement(
                MovementType.BREATHING_DEMO, duration=12.0, loop=True
            )

        elif event.event_type == "break_completed":
            self.movement_manager.start_movement(MovementType.NOD_YES, duration=1.0)
            self.movement_manager.queue_movement(MovementType.IDLE, duration=1.0)

        elif event.event_type == "timer_paused":
            self.movement_manager.start_movement(MovementType.IDLE, duration=1.0)

        elif event.event_type == "timer_resumed":
            if self.timer.state == TimerState.FOCUS:
                self.movement_manager.start_movement(
                    MovementType.BREATHING, duration=60.0, loop=True
                )

        elif event.event_type == "timer_stopped":
            self.movement_manager.start_movement(MovementType.IDLE, duration=1.0)

    def _start_compita(self) -> None:
        """Initialize and start Compita voice assistant."""
        if not self._compita_settings.enabled:
            self.logger.info("Compita is disabled")
            return

        try:
            from reachy_mini_pomodoro.voice.agent import CompitaVoiceAgent

            self._compita = CompitaVoiceAgent(
                timer=self.timer,
                task_manager=self.task_manager,
                movement_manager=self.movement_manager,
                openai_api_key=self._compita_settings.openai_api_key,
                model=self._compita_settings.model,
                voice=self._compita_settings.voice,
            )
            self._compita.start()
            self.logger.info("Compita voice assistant started")

        except ImportError as e:
            self.logger.warning(f"Compita dependencies not installed: {e}")
            self.logger.info("Install with: pip install openai")
        except ValueError as e:
            self.logger.warning(f"Compita not configured: {e}")
        except Exception as e:
            self.logger.error(f"Failed to start Compita: {e}")

    def _stop_compita(self) -> None:
        """Stop Compita voice assistant."""
        if self._compita:
            try:
                self._compita.stop()
                self.logger.info("Compita stopped")
            except Exception as e:
                self.logger.error(f"Error stopping Compita: {e}")
            self._compita = None

    def _start_robot_voice_loop(self) -> bool:
        """Start robot microphone voice loop for Compita.

        This uses the robot's built-in microphone instead of browser audio,
        which works when accessing the app over HTTP (not just HTTPS).

        Returns True if robot voice started successfully, False otherwise.
        """
        if not self._compita_settings.enabled:
            self.logger.info("Robot voice loop disabled (Compita is off)")
            return False

        if not self._compita_settings.openai_api_key:
            self.logger.info("Robot voice loop disabled (no API key)")
            return False

        if self._reachy_mini is None:
            self.logger.warning("No robot reference available for voice loop")
            return False

        try:
            if not hasattr(self._reachy_mini, 'media'):
                self.logger.info("No media available - using browser audio only")
                return False

            # Check if media backend is available
            try:
                from reachy_mini.media.media_manager import MediaBackend
                backend = self._reachy_mini.media.backend
                if backend == MediaBackend.NO_MEDIA:
                    self.logger.info("No media backend - using browser audio only")
                    return False
                self.logger.info(f"Media backend available: {backend}")
            except Exception as e:
                self.logger.warning(f"Could not check media backend: {e}")
                return False

            from reachy_mini_pomodoro.voice.robot_voice import RobotVoiceLoop

            self._robot_voice_loop = RobotVoiceLoop(
                robot=self._reachy_mini,
                timer=self.timer,
                task_manager=self.task_manager,
                movement_manager=self.movement_manager,
                openai_api_key=self._compita_settings.openai_api_key,
                voice=self._compita_settings.voice,
            )
            self._robot_voice_loop.start()
            self.logger.info("Robot voice loop started (using robot microphone)")
            return True

        except ImportError as e:
            self.logger.info(f"Robot voice dependencies not available: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"Could not start robot voice loop: {e}")
            return False

    def _stop_robot_voice_loop(self) -> None:
        """Stop the robot microphone voice loop."""
        if self._robot_voice_loop:
            try:
                self._robot_voice_loop.stop()
                self.logger.info("Robot voice loop stopped")
            except Exception as e:
                self.logger.error(f"Error stopping robot voice loop: {e}")
            self._robot_voice_loop = None

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        self.logger.info("Starting Reachy Mini Pomodoro app...")
        self._reachy_mini = reachy_mini  # Store robot reference for audio
        self._setup_api_endpoints()
        self.movement_manager.start_movement(MovementType.IDLE, duration=1.0, loop=True)

        robot_voice_started = self._start_robot_voice_loop()
        if not robot_voice_started:
            self._start_compita()

        loop_period = 1.0 / CONTROL_LOOP_FREQUENCY

        try:
            while not stop_event.is_set():
                loop_start = time.time()
                self.timer.update()
                head_pose, antennas, body_yaw = self.movement_manager.update()

                try:
                    reachy_mini.set_target(
                        head=head_pose,
                        antennas=antennas,
                        body_yaw=body_yaw,
                    )
                except Exception as e:
                    self.logger.warning(f"Error setting robot target: {e}")

                elapsed = time.time() - loop_start
                sleep_time = loop_period - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, stopping...")
        finally:
            self._stop_robot_voice_loop()
            self._stop_compita()
            self.logger.info("Pomodoro app stopped.")

    def _setup_api_endpoints(self) -> None:
        if self.settings_app is None:
            return

        @self.settings_app.get("/api/status")
        def get_status():
            return {
                "timer": self.timer.get_status(),
                "tasks": self.task_manager.to_dict(),
            }

        @self.settings_app.post("/api/timer/start")
        def start_timer():
            if not self.task_manager.get_current_task():
                pending = self.task_manager.get_pending_tasks()
                if pending:
                    self.task_manager.set_current_task(pending[0].id)
            success = self.timer.start_focus()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.post("/api/timer/pause")
        def pause_timer():
            success = self.timer.pause()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.post("/api/timer/resume")
        def resume_timer():
            success = self.timer.resume()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.post("/api/timer/stop")
        def stop_timer():
            success = self.timer.stop()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.post("/api/timer/skip")
        def skip_timer():
            success = self.timer.skip()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.post("/api/timer/break")
        def start_break():
            success = self.timer.start_break()
            return {"success": success, "status": self.timer.get_status()}

        @self.settings_app.get("/api/tasks")
        def get_tasks():
            return self.task_manager.to_dict()

        @self.settings_app.post("/api/tasks")
        def add_task(request: AddTaskRequest):
            task = self.task_manager.add_task(
                title=request.title,
                estimated_pomodoros=request.estimated_pomodoros,
                notes=request.notes,
                tags=request.tags,
                priority=request.priority,
                due_date=request.due_date,
            )
            self.movement_manager.start_movement(MovementType.NOD_YES, duration=1.0)
            return {"success": True, "task": task.to_dict()}

        @self.settings_app.put("/api/tasks/{task_id}")
        def update_task(task_id: str, request: UpdateTaskRequest):
            task = self.task_manager.update_task(
                task_id=task_id,
                title=request.title,
                estimated_pomodoros=request.estimated_pomodoros,
                notes=request.notes,
                tags=request.tags,
                priority=request.priority,
                due_date=request.due_date,
            )
            if task:
                return {"success": True, "task": task.to_dict()}
            return {"success": False, "error": "Task not found"}

        @self.settings_app.delete("/api/tasks/{task_id}")
        def delete_task(task_id: str):
            success = self.task_manager.delete_task(task_id)
            if success:
                self.movement_manager.start_movement(MovementType.NOD_NO, duration=0.8)
            return {"success": success}

        @self.settings_app.post("/api/tasks/{task_id}/select")
        def select_task(task_id: str):
            task = self.task_manager.set_current_task(task_id)
            if task:
                return {"success": True, "task": task.to_dict()}
            return {"success": False, "error": "Task not found or already completed"}

        @self.settings_app.post("/api/tasks/{task_id}/complete")
        async def complete_task(task_id: str):
            self.logger.info(f"Complete task endpoint called for task_id: {task_id}")
            task = self.task_manager.complete_task(task_id)
            if task:
                self.logger.info(f"Task found, starting CELEBRATION movement")
                self.movement_manager.start_movement(
                    MovementType.CELEBRATION, duration=3.0
                )
                # Notify voice session about task completion
                if self._active_voice_session:
                    try:
                        await self._active_voice_session.notify_event(
                            f"The user just completed a task called '{task.title}'. "
                            "Congratulate them briefly and enthusiastically!"
                        )
                    except Exception as e:
                        self.logger.debug(f"Could not notify voice session: {e}")
                return {"success": True, "task": task.to_dict()}
            self.logger.warning(f"Task not found for task_id: {task_id}")
            return {"success": False, "error": "Task not found"}

        @self.settings_app.post("/api/tasks/reorder")
        def reorder_tasks(request: ReorderTasksRequest):
            success = self.task_manager.reorder_tasks(request.task_ids)
            return {"success": success}

        @self.settings_app.post("/api/tasks/clear-completed")
        def clear_completed():
            count = self.task_manager.clear_completed()
            return {"success": True, "removed_count": count}

        @self.settings_app.get("/api/tags")
        def get_tags():
            return {"tags": self.task_manager.get_all_tags()}

        @self.settings_app.post("/api/tags")
        def create_tag(name: str, color: Optional[str] = None):
            if self.task_manager.db:
                tag = self.task_manager.db.save_tag(name, color)
                return {"success": True, "tag": tag}
            return {"success": False, "error": "Database not available"}

        @self.settings_app.post("/api/tags/filter")
        def set_tag_filter(tag: Optional[str] = None):
            self.task_manager.set_tag_filter(tag)
            return {"success": True, "filter": self.task_manager.tag_filter}

        @self.settings_app.delete("/api/tags/filter")
        def clear_tag_filter():
            self.task_manager.set_tag_filter(None)
            return {"success": True, "filter": None}

        @self.settings_app.get("/api/history")
        def get_history(days: int = 7):
            return self.task_manager.get_history(days)

        @self.settings_app.get("/api/stats")
        def get_stats():
            return self.task_manager.get_stats()

        @self.settings_app.get("/api/settings")
        def get_settings():
            return self.timer.get_status()["settings"]

        @self.settings_app.put("/api/settings")
        def update_settings(request: UpdateSettingsRequest):
            self.timer.update_settings(
                focus_duration=request.focus_duration,
                short_break_duration=request.short_break_duration,
                long_break_duration=request.long_break_duration,
                pomodoros_until_long_break=request.pomodoros_until_long_break,
            )
            return {"success": True, "settings": self.timer.get_status()["settings"]}

        @self.settings_app.post("/api/robot/celebrate")
        def robot_celebrate():
            self.movement_manager.start_movement(MovementType.CELEBRATION, duration=3.0)
            return {"success": True}

        @self.settings_app.post("/api/robot/demo-stretch")
        def robot_demo_stretch():
            self.movement_manager.start_movement(
                MovementType.STRETCH_DEMO, duration=8.0
            )
            return {"success": True}

        @self.settings_app.post("/api/robot/demo-breathing")
        def robot_demo_breathing():
            self.movement_manager.start_movement(
                MovementType.BREATHING_DEMO, duration=12.0
            )
            return {"success": True}

        @self.settings_app.get("/api/compita/status")
        def get_compita_status():
            """Get Compita voice assistant status."""
            import os
            # Check both dashboard setting and environment variable
            has_api_key = bool(
                self._compita_settings.openai_api_key or os.getenv("OPENAI_API_KEY")
            )
            robot_voice_running = (
                self._robot_voice_loop is not None
                and self._robot_voice_loop.is_running()
            )
            legacy_running = self._compita is not None and self._compita.is_running()

            if robot_voice_running:
                voice_mode = "robot"
            elif legacy_running:
                voice_mode = "legacy"
            else:
                voice_mode = "browser"

            robot_voice_debug = {}
            if self._robot_voice_loop:
                robot_voice_debug = {
                    "input_sample_rate": getattr(self._robot_voice_loop, "_input_sample_rate", None),
                    "output_sample_rate": getattr(self._robot_voice_loop, "_output_sample_rate", None),
                    "session_active": self._robot_voice_loop._session is not None if hasattr(self._robot_voice_loop, "_session") else False,
                }

            return {
                "enabled": self._compita_settings.enabled,
                "running": robot_voice_running or legacy_running,
                "has_api_key": has_api_key,
                "voice_mode": voice_mode,
                "robot_voice_available": self._reachy_mini is not None,
                "robot_voice_debug": robot_voice_debug,
            }

        @self.settings_app.post("/api/compita/activate")
        async def activate_compita():
            """Manually activate Compita (useful when wake word detection isn't available)."""
            if self._robot_voice_loop and self._robot_voice_loop._session:
                await self._robot_voice_loop._session.activate()
                return {"success": True, "message": "Compita activated"}
            elif self._compita_session:
                await self._compita_session.activate()
                return {"success": True, "message": "Compita activated"}
            return {"success": False, "message": "No active voice session"}

        @self.settings_app.get("/api/compita/debug")
        def get_compita_debug():
            """Get detailed debug info for Compita voice."""
            debug = {
                "robot_voice_loop": None,
                "session": None,
                "agent": None,
            }

            if self._robot_voice_loop:
                debug["robot_voice_loop"] = {
                    "running": self._robot_voice_loop._running,
                    "input_sample_rate": self._robot_voice_loop._input_sample_rate,
                    "output_sample_rate": self._robot_voice_loop._output_sample_rate,
                    "has_session": self._robot_voice_loop._session is not None,
                    "audio_rms": getattr(self._robot_voice_loop, "_last_audio_rms", 0),
                    "audio_max": getattr(self._robot_voice_loop, "_last_audio_max", 0),
                }

                if self._robot_voice_loop._session:
                    session = self._robot_voice_loop._session
                    debug["session"] = {
                        "state": session._state.value,
                        "running": session._running,
                        "has_agent": session._agent is not None,
                    }

                    if session._agent:
                        agent = session._agent
                        debug["agent"] = {
                            "running": agent._running,
                            "has_connection": agent._connection is not None,
                            "audio_chunks_sent": agent._audio_chunks_sent,
                            "audio_chunks_received": getattr(agent, "_audio_chunks_received", 0),
                            "speech_detected": getattr(agent, "_speech_detected", False),
                            "last_event": getattr(agent, "_last_event", ""),
                            "last_error": getattr(agent, "_last_error", ""),
                        }

            return debug

        @self.settings_app.get("/api/compita/settings")
        def get_compita_settings():
            """Get Compita voice assistant settings."""
            api_key = self._compita_settings.openai_api_key
            masked_key = ""
            if api_key:
                if len(api_key) > 8:
                    masked_key = api_key[:7] + "..." + api_key[-4:]
                else:
                    masked_key = "••••••••"

            return {
                "enabled": self._compita_settings.enabled,
                "openai_api_key": masked_key,
                "voice": self._compita_settings.voice,
                "has_api_key": bool(api_key),
            }

        @self.settings_app.put("/api/compita/settings")
        def update_compita_settings(request: UpdateCompitaSettingsRequest):
            """Update Compita voice assistant settings."""
            restart_needed = False

            if request.enabled is not None:
                self._compita_settings.enabled = request.enabled
                restart_needed = True

            if request.openai_api_key is not None:
                # Only update if it's a new key (not masked)
                new_key = request.openai_api_key.strip()
                if new_key and not new_key.startswith("•") and new_key != "":
                    self._compita_settings.openai_api_key = new_key
                    restart_needed = True

            if request.voice is not None:
                valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral"]
                if request.voice in valid_voices:
                    self._compita_settings.voice = request.voice
                    restart_needed = True

            if restart_needed:
                self._stop_robot_voice_loop()
                self._stop_compita()

                if self._compita_settings.enabled:
                    robot_voice_started = self._start_robot_voice_loop()
                    if not robot_voice_started:
                        self._start_compita()

            return {
                "success": True,
                "settings": {
                    "enabled": self._compita_settings.enabled,
                    "voice": self._compita_settings.voice,
                    "has_api_key": bool(self._compita_settings.openai_api_key),
                }
            }

        @self.settings_app.websocket("/api/compita/stream")
        async def compita_stream(websocket: WebSocket):
            """WebSocket endpoint for browser-based voice streaming.

            Uses wake word detection - listens for "Compita" to activate,
            then returns to listening after conversation timeout.
            """
            await websocket.accept()
            self.logger.info("Browser voice client connected")

            try:
                from reachy_mini_pomodoro.voice.agent import (
                    CompitaVoiceSession,
                    SessionState,
                )

                # Create callbacks for this WebSocket
                async def send_audio(audio_bytes: bytes):
                    try:
                        await websocket.send_bytes(audio_bytes)
                    except Exception:
                        pass

                async def send_transcript(role: str, text: str):
                    try:
                        await websocket.send_json({
                            "type": "transcript",
                            "role": role,
                            "text": text,
                        })
                    except Exception:
                        pass

                async def send_state(state: SessionState):
                    try:
                        await websocket.send_json({
                            "type": "state",
                            "state": state.value,
                        })
                    except Exception:
                        pass

                # Create session with wake word detection
                # Pass None if no API key set so it falls back to env var
                api_key = self._compita_settings.openai_api_key or None
                session = CompitaVoiceSession(
                    timer=self.timer,
                    task_manager=self.task_manager,
                    movement_manager=self.movement_manager,
                    openai_api_key=api_key,
                    model=self._compita_settings.model,
                    voice=self._compita_settings.voice,
                    on_audio_output=lambda b: asyncio.create_task(send_audio(b)),
                    on_transcript=lambda r, t: asyncio.create_task(send_transcript(r, t)),
                    on_state_change=lambda s: asyncio.create_task(send_state(s)),
                )
                session.start()
                self._active_voice_session = session  # Store for notifications

                # Start timeout checker in background
                timeout_task = asyncio.create_task(session.run_timeout_checker())

                # Receive audio/messages from browser
                try:
                    while True:
                        data = await websocket.receive()
                        msg_type = data.get("type", "")

                        # Check for disconnect
                        if msg_type == "websocket.disconnect":
                            break

                        if "bytes" in data:
                            await session.process_audio(data["bytes"])
                        elif "text" in data:
                            msg = data["text"]
                            if msg == "close":
                                break
                            # Handle wake word from browser speech recognition
                            elif msg.startswith("transcript:"):
                                text = msg[11:]
                                self.logger.info(f"Received transcript: {text}")
                                await session.handle_user_transcript(text)
                            # Manual activation (button press)
                            elif msg == "activate":
                                await session.activate()
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    self.logger.debug(f"WebSocket receive error: {e}")
                finally:
                    session.stop()
                    timeout_task.cancel()

            except Exception as e:
                self.logger.error(f"Voice stream error: {e}")
            finally:
                self.logger.info("Browser voice client disconnected")

    def wrapped_run(self) -> None:
        settings_app_t = None
        if self.settings_app is not None:
            assert self.custom_app_url is not None
            url = urlparse(self.custom_app_url)
            assert url.hostname is not None and url.port is not None

            config = uvicorn.Config(
                self.settings_app,
                host=url.hostname,
                port=url.port,
            )
            server = uvicorn.Server(config)

            def _server_run() -> None:
                t = threading.Thread(target=server.run)
                t.start()
                self.stop_event.wait()
                server.should_exit = True
                t.join()

            settings_app_t = threading.Thread(target=_server_run)
            settings_app_t.start()

        try:
            media_backend = self._media_backend_override or self.media_backend
            self.logger.info("Starting Reachy Mini app...")
            self.logger.info(f"Using media backend: {media_backend}")
            self.logger.info(f"Localhost only: {self.localhost_only}")
            with ReachyMini(
                media_backend=media_backend,
                localhost_only=self.localhost_only,
            ) as reachy_mini:
                self.run(reachy_mini, self.stop_event)
        except Exception:
            self.error = traceback.format_exc()
            raise
        finally:
            if settings_app_t is not None:
                self.stop_event.set()
                settings_app_t.join()


if __name__ == "__main__":
    app = ReachyMiniPomodoro()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
