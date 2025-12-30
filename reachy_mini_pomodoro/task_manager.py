"""Task management for the Pomodoro app."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from reachy_mini_pomodoro.database import PomodoroDatabase, TaskRecord


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskPriority(Enum):
    """Priority level of a task."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Task:
    """A task in the Pomodoro todo list."""
    id: str
    title: str
    estimated_pomodoros: int
    completed_pomodoros: int = 0
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[date] = None
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    notes: str = ""

    def to_dict(self) -> dict:
        """Convert task to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "estimated_pomodoros": self.estimated_pomodoros,
            "completed_pomodoros": self.completed_pomodoros,
            "status": self.status.value,
            "priority": self.priority.value,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """Create a task from a dictionary."""
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        due_date = None
        if data.get("due_date"):
            due_date = date.fromisoformat(data["due_date"])
        return cls(
            id=data["id"],
            title=data["title"],
            estimated_pomodoros=data["estimated_pomodoros"],
            completed_pomodoros=data.get("completed_pomodoros", 0),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "medium")),
            due_date=due_date,
            tags=tags,
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            notes=data.get("notes", ""),
        )

    def to_db_record(self) -> TaskRecord:
        """Convert to database record."""
        return TaskRecord(
            id=self.id,
            title=self.title,
            estimated_pomodoros=self.estimated_pomodoros,
            completed_pomodoros=self.completed_pomodoros,
            status=self.status.value,
            priority=self.priority.value,
            due_date=self.due_date,
            tags=",".join(self.tags),
            created_at=self.created_at,
            completed_at=self.completed_at,
            notes=self.notes,
        )

    @classmethod
    def from_db_record(cls, record: TaskRecord) -> "Task":
        """Create from database record."""
        tags = [t.strip() for t in record.tags.split(",") if t.strip()]
        return cls(
            id=record.id,
            title=record.title,
            estimated_pomodoros=record.estimated_pomodoros,
            completed_pomodoros=record.completed_pomodoros,
            status=TaskStatus(record.status),
            priority=TaskPriority(record.priority or "medium"),
            due_date=record.due_date,
            tags=tags,
            created_at=record.created_at,
            completed_at=record.completed_at,
            notes=record.notes,
        )


class TaskManager:
    """Manages the task list for the Pomodoro app."""

    def __init__(self, use_database: bool = True) -> None:
        self.tasks: List[Task] = []
        self.current_task_id: Optional[str] = None
        self.total_pomodoros_today: int = 0
        self.session_start: datetime = datetime.now()
        self.tag_filter: Optional[str] = None  # Current tag filter

        # Database for persistence
        self.db: Optional[PomodoroDatabase] = None
        if use_database:
            self.db = PomodoroDatabase()
            self._load_from_db()

    def _load_from_db(self) -> None:
        """Load tasks from database."""
        if not self.db:
            return
        records = self.db.get_all_tasks(include_completed=True)
        self.tasks = [Task.from_db_record(r) for r in records]

        # Load today's stats
        stats = self.db.get_daily_stats()
        self.total_pomodoros_today = stats["total_pomodoros"]

    def _save_task_to_db(self, task: Task) -> None:
        """Save a task to the database."""
        if self.db:
            self.db.save_task(task.to_db_record())

    def add_task(self, title: str, estimated_pomodoros: int = 1,
                 notes: str = "", tags: Optional[List[str]] = None,
                 priority: str = "medium", due_date: Optional[str] = None) -> Task:
        """Add a new task to the list."""
        parsed_due_date = None
        if due_date:
            parsed_due_date = date.fromisoformat(due_date)
        task = Task(
            id=str(uuid.uuid4())[:8],
            title=title,
            estimated_pomodoros=max(1, min(estimated_pomodoros, 8)),
            notes=notes,
            tags=tags or [],
            priority=TaskPriority(priority),
            due_date=parsed_due_date,
        )
        self.tasks.insert(0, task)
        self._save_task_to_db(task)

        if self.db and tags:
            for tag in tags:
                self.db.save_tag(tag)

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_current_task(self) -> Optional[Task]:
        """Get the currently active task."""
        if self.current_task_id:
            return self.get_task(self.current_task_id)
        return None

    def set_current_task(self, task_id: str) -> Optional[Task]:
        """Set the current task by ID."""
        task = self.get_task(task_id)
        if task and task.status != TaskStatus.COMPLETED:
            # Mark previous task as pending if it was in progress
            if self.current_task_id and self.current_task_id != task_id:
                prev_task = self.get_task(self.current_task_id)
                if prev_task and prev_task.status == TaskStatus.IN_PROGRESS:
                    prev_task.status = TaskStatus.PENDING
                    self._save_task_to_db(prev_task)

            self.current_task_id = task_id
            task.status = TaskStatus.IN_PROGRESS
            self._save_task_to_db(task)
            return task
        return None

    def complete_pomodoro(self) -> Optional[Task]:
        """Mark one pomodoro as completed for the current task."""
        task = self.get_current_task()
        if task:
            task.completed_pomodoros += 1
            self.total_pomodoros_today += 1
            self._save_task_to_db(task)

            # Check if task is complete
            if task.completed_pomodoros >= task.estimated_pomodoros:
                self.complete_task(task.id)

            return task
        return None

    def complete_task(self, task_id: str) -> Optional[Task]:
        """Mark a task as completed."""
        task = self.get_task(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            self._save_task_to_db(task)

            if self.db:
                self.db.increment_tasks_completed()

            if self.current_task_id == task_id:
                self.current_task_id = None
                # Auto-select next pending task
                self._select_next_task()
            return task
        return None

    def _select_next_task(self) -> None:
        """Automatically select the next pending task."""
        for task in self.tasks:
            if task.status == TaskStatus.PENDING:
                self.current_task_id = task.id
                task.status = TaskStatus.IN_PROGRESS
                self._save_task_to_db(task)
                break

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID."""
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                if self.current_task_id == task_id:
                    self.current_task_id = None
                self.tasks.pop(i)
                if self.db:
                    self.db.delete_task(task_id)
                return True
        return False

    def reorder_tasks(self, task_ids: List[str]) -> bool:
        """Reorder tasks based on the provided list of IDs."""
        # Validate all IDs exist
        existing_ids = {task.id for task in self.tasks}
        if set(task_ids) != existing_ids:
            return False

        # Create new ordered list
        task_map = {task.id: task for task in self.tasks}
        self.tasks = [task_map[tid] for tid in task_ids]
        return True

    def update_task(self, task_id: str, title: Optional[str] = None,
                    estimated_pomodoros: Optional[int] = None,
                    notes: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    priority: Optional[str] = None,
                    due_date: Optional[str] = None) -> Optional[Task]:
        """Update task properties."""
        task = self.get_task(task_id)
        if task:
            if title is not None:
                task.title = title
            if estimated_pomodoros is not None:
                task.estimated_pomodoros = max(1, min(estimated_pomodoros, 8))
            if notes is not None:
                task.notes = notes
            if tags is not None:
                task.tags = tags
                if self.db:
                    for tag in tags:
                        self.db.save_tag(tag)
            if priority is not None:
                task.priority = TaskPriority(priority)
            if due_date is not None:
                task.due_date = date.fromisoformat(due_date) if due_date else None
            self._save_task_to_db(task)
            return task
        return None

    def set_tag_filter(self, tag: Optional[str]) -> None:
        """Set a tag filter for task listing."""
        self.tag_filter = tag.lower().strip() if tag else None

    def get_filtered_tasks(self) -> List[Task]:
        """Get tasks filtered by current tag filter."""
        if not self.tag_filter:
            return self.tasks
        return [t for t in self.tasks if self.tag_filter in [tag.lower() for tag in t.tags]]

    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        tasks = self.get_filtered_tasks()
        return [t for t in tasks if t.status == TaskStatus.PENDING]

    def get_in_progress_tasks(self) -> List[Task]:
        """Get all in-progress tasks."""
        tasks = self.get_filtered_tasks()
        return [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]

    def get_completed_tasks(self) -> List[Task]:
        """Get all completed tasks."""
        tasks = self.get_filtered_tasks()
        return [t for t in tasks if t.status == TaskStatus.COMPLETED]

    def get_all_tags(self) -> List[dict]:
        """Get all available tags."""
        if self.db:
            return self.db.get_all_tags()
        # Fallback: extract from tasks
        tags = set()
        for task in self.tasks:
            tags.update(task.tags)
        return [{"name": tag, "color": "#3498db"} for tag in sorted(tags)]

    def get_stats(self) -> dict:
        """Get productivity statistics."""
        completed = self.get_completed_tasks()
        pending = self.get_pending_tasks()
        current = self.get_current_task()

        total_estimated = sum(t.estimated_pomodoros for t in self.tasks)
        total_completed = sum(t.completed_pomodoros for t in self.tasks)

        return {
            "total_tasks": len(self.tasks),
            "completed_tasks": len(completed),
            "pending_tasks": len(pending),
            "current_task": current.to_dict() if current else None,
            "total_pomodoros_today": self.total_pomodoros_today,
            "total_estimated_pomodoros": total_estimated,
            "total_completed_pomodoros": total_completed,
            "progress_percentage": (total_completed / total_estimated * 100) if total_estimated > 0 else 0,
            "tag_filter": self.tag_filter,
        }

    def get_history(self, days: int = 7) -> dict:
        """Get history summary."""
        if self.db:
            return self.db.get_history_summary(days)
        return {
            "days": days,
            "total_sessions": 0,
            "focus_sessions": 0,
            "total_focus_minutes": 0,
            "completed_tasks": 0,
        }

    def to_dict(self) -> dict:
        """Convert entire task manager state to dictionary."""
        filtered_tasks = self.get_filtered_tasks()
        return {
            "tasks": [t.to_dict() for t in filtered_tasks],
            "current_task_id": self.current_task_id,
            "stats": self.get_stats(),
            "tags": self.get_all_tags(),
        }

    def clear_completed(self) -> int:
        """Remove all completed tasks. Returns count of removed tasks."""
        initial_count = len(self.tasks)
        completed_ids = [t.id for t in self.tasks if t.status == TaskStatus.COMPLETED]
        self.tasks = [t for t in self.tasks if t.status != TaskStatus.COMPLETED]

        # Note: We don't delete from DB to keep history
        return initial_count - len(self.tasks)
