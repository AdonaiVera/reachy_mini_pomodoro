"""Main Pomodoro app for Reachy Mini."""

import logging
import threading
import time
import traceback
from typing import List, Optional
from urllib.parse import urlparse

import uvicorn
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


class ReachyMiniPomodoro(ReachyMiniApp):
    """Pomodoro productivity timer app with Reachy Mini robot companion."""

    custom_app_url: str | None = CUSTOM_APP_URL
    request_media_backend: str | None = "no_media"

    def __init__(
        self,
        localhost_only: bool = True,
        compita_settings: Optional[CompitaSettings] = None,
    ) -> None:
        super().__init__()
        self.localhost_only = localhost_only
        self.logger = logging.getLogger("reachy_mini.pomodoro")
        self.task_manager = TaskManager()
        self.timer = PomodoroTimer()
        self.movement_manager = MovementManager()
        self.timer.add_event_listener(self._handle_timer_event)
        self._sound_enabled = True
        self._compita_settings = compita_settings or DEFAULT_COMPITA_SETTINGS
        self._compita = None

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

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        self.logger.info("Starting Reachy Mini Pomodoro app...")
        self._setup_api_endpoints()
        self.movement_manager.start_movement(MovementType.IDLE, duration=1.0, loop=True)

        # Start Compita voice assistant
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
        def complete_task(task_id: str):
            task = self.task_manager.complete_task(task_id)
            if task:
                self.movement_manager.start_movement(
                    MovementType.CELEBRATION, duration=3.0
                )
                return {"success": True, "task": task.to_dict()}
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
            if self._compita:
                return {
                    "enabled": True,
                    "running": self._compita.is_running(),
                }
            return {"enabled": False, "running": False}

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
            self.logger.info("Starting Reachy Mini app...")
            self.logger.info(f"Using media backend: {self.media_backend}")
            self.logger.info(f"Localhost only: {self.localhost_only}")
            with ReachyMini(
                media_backend=self.media_backend,
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
