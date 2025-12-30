"""Compita - Pomodoro tools for the OpenAI Realtime API.

These tools allow the LLM to interact with the Pomodoro app
to control the timer, manage tasks, and retrieve status.
"""

import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from reachy_mini_pomodoro.pomodoro_timer import PomodoroTimer
    from reachy_mini_pomodoro.task_manager import TaskManager

logger = logging.getLogger(__name__)


def get_pomodoro_tools() -> List[Dict[str, Any]]:
    """Get tool specifications for OpenAI Realtime API."""
    return [
        {
            "type": "function",
            "name": "get_timer_status",
            "description": "Get the current status of the Pomodoro timer, including state, time remaining, and current task.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "start_focus",
            "description": "Start a focus session. This begins the Pomodoro timer for focused work.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "pause_timer",
            "description": "Pause the current timer (focus or break).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "resume_timer",
            "description": "Resume a paused timer.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "stop_timer",
            "description": "Stop the current timer and reset to idle state.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "start_break",
            "description": "Start a break session after completing a focus session.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "get_tasks",
            "description": "Get the list of pending tasks.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "create_task",
            "description": "Create a new task to work on.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the task.",
                    },
                    "estimated_pomodoros": {
                        "type": "integer",
                        "description": "Estimated number of pomodoros to complete the task (default: 1).",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Priority level of the task (default: medium).",
                    },
                },
                "required": ["title"],
            },
        },
        {
            "type": "function",
            "name": "complete_current_task",
            "description": "Mark the current task as completed.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "type": "function",
            "name": "get_stats",
            "description": "Get productivity statistics including pomodoros completed today and tasks finished.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    ]


class PomodoroToolHandler:
    """Handles execution of Pomodoro tools called by the LLM."""

    def __init__(
        self,
        timer: "PomodoroTimer",
        task_manager: "TaskManager",
    ) -> None:
        self.timer = timer
        self.task_manager = task_manager

    async def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name and return the result."""
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return await handler(**arguments)
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}

    async def _handle_get_timer_status(self) -> Dict[str, Any]:
        """Get current timer status."""
        status = self.timer.get_status()
        current_task = self.task_manager.get_current_task()

        remaining = status["remaining_seconds"]
        minutes = remaining // 60
        seconds = remaining % 60

        return {
            "state": status["state"],
            "time_remaining": f"{minutes} minutes and {seconds} seconds",
            "current_task": current_task.title if current_task else None,
            "session_count": status.get("session_count", 0),
        }

    async def _handle_start_focus(self) -> Dict[str, Any]:
        """Start a focus session."""
        if not self.task_manager.get_current_task():
            pending = self.task_manager.get_pending_tasks()
            if pending:
                self.task_manager.set_current_task(pending[0].id)

        success = self.timer.start_focus()
        task = self.task_manager.get_current_task()

        return {
            "success": success,
            "message": "Focus session started!" if success else "Could not start focus session",
            "current_task": task.title if task else None,
        }

    async def _handle_pause_timer(self) -> Dict[str, Any]:
        """Pause the timer."""
        success = self.timer.pause()
        return {
            "success": success,
            "message": "Timer paused" if success else "Could not pause timer",
        }

    async def _handle_resume_timer(self) -> Dict[str, Any]:
        """Resume the timer."""
        success = self.timer.resume()
        return {
            "success": success,
            "message": "Timer resumed" if success else "Could not resume timer",
        }

    async def _handle_stop_timer(self) -> Dict[str, Any]:
        """Stop the timer."""
        success = self.timer.stop()
        return {
            "success": success,
            "message": "Timer stopped" if success else "Could not stop timer",
        }

    async def _handle_start_break(self) -> Dict[str, Any]:
        """Start a break session."""
        success = self.timer.start_break()
        status = self.timer.get_status()
        break_type = "long" if status["state"] == "long_break" else "short"

        return {
            "success": success,
            "message": f"Starting {break_type} break!" if success else "Could not start break",
            "break_type": break_type if success else None,
        }

    async def _handle_get_tasks(self) -> Dict[str, Any]:
        """Get list of tasks."""
        pending = self.task_manager.get_pending_tasks()
        current = self.task_manager.get_current_task()

        tasks = []
        for task in pending:
            tasks.append({
                "title": task.title,
                "pomodoros": f"{task.completed_pomodoros}/{task.estimated_pomodoros}",
                "is_current": current and task.id == current.id,
                "priority": task.priority,
            })

        return {
            "count": len(pending),
            "tasks": tasks,
        }

    async def _handle_create_task(
        self,
        title: str,
        estimated_pomodoros: int = 1,
        priority: str = "medium",
    ) -> Dict[str, Any]:
        """Create a new task."""
        task = self.task_manager.add_task(
            title=title,
            estimated_pomodoros=estimated_pomodoros,
            priority=priority,
        )
        return {
            "success": True,
            "message": f"Task '{title}' created",
            "task_id": task.id,
        }

    async def _handle_complete_current_task(self) -> Dict[str, Any]:
        """Complete the current task."""
        current = self.task_manager.get_current_task()
        if not current:
            return {"success": False, "message": "No current task to complete"}

        task = self.task_manager.complete_task(current.id)
        if task:
            return {
                "success": True,
                "message": f"Task '{task.title}' completed!",
            }
        return {"success": False, "message": "Could not complete task"}

    async def _handle_get_stats(self) -> Dict[str, Any]:
        """Get productivity statistics."""
        stats = self.task_manager.get_stats()
        timer_status = self.timer.get_status()

        return {
            "today_pomodoros": stats.get("today", {}).get("pomodoros", 0),
            "today_tasks_completed": stats.get("today", {}).get("tasks_completed", 0),
            "current_session": timer_status.get("session_count", 0),
        }
