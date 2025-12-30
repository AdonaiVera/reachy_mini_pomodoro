"""SQLite database for Pomodoro app persistence and history."""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".reachy_pomodoro" / "pomodoro.db"

TAG_COLORS = [
    "#e74c3c",  # Red
    "#3498db",  # Blue
    "#27ae60",  # Green
    "#f39c12",  # Orange
    "#9b59b6",  # Purple
    "#1abc9c",  # Teal
    "#e91e63",  # Pink
    "#00bcd4",  # Cyan
]


@dataclass
class PomodoroSession:
    """A completed pomodoro session."""

    id: Optional[int]
    task_id: str
    task_title: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: int
    session_type: str
    tags: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "session_type": self.session_type,
            "tags": self.tags,
        }


@dataclass
class TaskRecord:
    """A task record in the database."""

    id: str
    title: str
    estimated_pomodoros: int
    completed_pomodoros: int
    status: str
    priority: str
    due_date: Optional[date]
    tags: str
    created_at: datetime
    completed_at: Optional[datetime]
    notes: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "estimated_pomodoros": self.estimated_pomodoros,
            "completed_pomodoros": self.completed_pomodoros,
            "status": self.status,
            "priority": self.priority,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "tags": self.tags,
            "tags_list": [t.strip() for t in self.tags.split(",") if t.strip()],
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "notes": self.notes,
        }


class PomodoroDatabase:
    """SQLite database manager for the Pomodoro app."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _migrate_db(self, cursor: sqlite3.Cursor) -> None:
        """Add new columns if they don't exist (for existing databases)."""
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1] for row in cursor.fetchall()}

        if "priority" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'")
            logger.info("Added 'priority' column to tasks table")

        if "due_date" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN due_date DATE")
            logger.info("Added 'due_date' column to tasks table")

    def _init_db(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                estimated_pomodoros INTEGER DEFAULT 1,
                completed_pomodoros INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                due_date DATE,
                tags TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        """)

        self._migrate_db(cursor)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                task_title TEXT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP NOT NULL,
                duration_seconds INTEGER NOT NULL,
                session_type TEXT NOT NULL,
                tags TEXT DEFAULT '',
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_pomodoros INTEGER DEFAULT 0,
                total_focus_minutes INTEGER DEFAULT 0,
                tasks_completed INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                name TEXT PRIMARY KEY,
                color TEXT DEFAULT '#3498db',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def save_task(self, task: TaskRecord) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO tasks
            (id, title, estimated_pomodoros, completed_pomodoros, status, priority, due_date, tags, created_at, completed_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.id,
                task.title,
                task.estimated_pomodoros,
                task.completed_pomodoros,
                task.status,
                task.priority,
                task.due_date.isoformat() if task.due_date else None,
                task.tags,
                task.created_at,
                task.completed_at,
                task.notes,
            ),
        )
        conn.commit()
        conn.close()

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return self._row_to_task(row)
        return None

    def get_all_tasks(self, include_completed: bool = True) -> List[TaskRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()
        if include_completed:
            cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        else:
            cursor.execute(
                "SELECT * FROM tasks WHERE status != 'completed' ORDER BY created_at DESC"
            )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_task(row) for row in rows]

    def get_tasks_by_tag(self, tag: str) -> List[TaskRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE tags LIKE ? ORDER BY created_at DESC",
            (f"%{tag}%",),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_task(row) for row in rows]

    def get_tasks_by_status(self, status: str) -> List[TaskRecord]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC", (status,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_task(row) for row in rows]

    def delete_task(self, task_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord:
        due_date = None
        if row["due_date"]:
            due_date = date.fromisoformat(row["due_date"])
        return TaskRecord(
            id=row["id"],
            title=row["title"],
            estimated_pomodoros=row["estimated_pomodoros"],
            completed_pomodoros=row["completed_pomodoros"],
            status=row["status"],
            priority=row["priority"] or "medium",
            due_date=due_date,
            tags=row["tags"] or "",
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else datetime.now()
            ),
            completed_at=(
                datetime.fromisoformat(row["completed_at"])
                if row["completed_at"]
                else None
            ),
            notes=row["notes"] or "",
        )

    def save_pomodoro_session(self, session: PomodoroSession) -> int:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO pomodoro_sessions
            (task_id, task_title, started_at, completed_at, duration_seconds, session_type, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.task_id,
                session.task_title,
                session.started_at,
                session.completed_at,
                session.duration_seconds,
                session.session_type,
                session.tags,
            ),
        )
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        self._update_daily_stats(session)
        return session_id

    def get_sessions_by_date(self, target_date: date) -> List[PomodoroSession]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pomodoro_sessions
            WHERE date(completed_at) = ?
            ORDER BY completed_at DESC
            """,
            (target_date.isoformat(),),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_session(row) for row in rows]

    def get_sessions_by_task(self, task_id: str) -> List[PomodoroSession]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pomodoro_sessions
            WHERE task_id = ?
            ORDER BY completed_at DESC
            """,
            (task_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_session(row) for row in rows]

    def get_recent_sessions(self, limit: int = 50) -> List[PomodoroSession]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM pomodoro_sessions
            ORDER BY completed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_session(row) for row in rows]

    def _row_to_session(self, row: sqlite3.Row) -> PomodoroSession:
        return PomodoroSession(
            id=row["id"],
            task_id=row["task_id"],
            task_title=row["task_title"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]),
            duration_seconds=row["duration_seconds"],
            session_type=row["session_type"],
            tags=row["tags"] or "",
        )

    def _update_daily_stats(self, session: PomodoroSession) -> None:
        if session.session_type != "focus":
            return

        today = session.completed_at.date().isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO daily_stats (date, total_pomodoros, total_focus_minutes, tasks_completed)
            VALUES (?, 1, ?, 0)
            ON CONFLICT(date) DO UPDATE SET
                total_pomodoros = total_pomodoros + 1,
                total_focus_minutes = total_focus_minutes + ?
            """,
            (today, session.duration_seconds // 60, session.duration_seconds // 60),
        )

        conn.commit()
        conn.close()

    def increment_tasks_completed(self, target_date: Optional[date] = None) -> None:
        target = (target_date or date.today()).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_stats (date, total_pomodoros, total_focus_minutes, tasks_completed)
            VALUES (?, 0, 0, 1)
            ON CONFLICT(date) DO UPDATE SET
                tasks_completed = tasks_completed + 1
            """,
            (target,),
        )
        conn.commit()
        conn.close()

    def get_daily_stats(self, target_date: Optional[date] = None) -> dict:
        target = (target_date or date.today()).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_stats WHERE date = ?", (target,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "date": row["date"],
                "total_pomodoros": row["total_pomodoros"],
                "total_focus_minutes": row["total_focus_minutes"],
                "tasks_completed": row["tasks_completed"],
            }
        return {
            "date": target,
            "total_pomodoros": 0,
            "total_focus_minutes": 0,
            "tasks_completed": 0,
        }

    def get_stats_range(self, start_date: date, end_date: date) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM daily_stats
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
            """,
            (start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "date": row["date"],
                "total_pomodoros": row["total_pomodoros"],
                "total_focus_minutes": row["total_focus_minutes"],
                "tasks_completed": row["tasks_completed"],
            }
            for row in rows
        ]

    def save_tag(self, name: str, color: Optional[str] = None) -> dict:
        name = name.lower().strip()
        if not color:
            existing_count = len(self.get_all_tags())
            color = TAG_COLORS[existing_count % len(TAG_COLORS)]

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT color FROM tags WHERE name = ?", (name,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return {"name": name, "color": existing["color"]}

        cursor.execute(
            "INSERT INTO tags (name, color) VALUES (?, ?)",
            (name, color),
        )
        conn.commit()
        conn.close()
        return {"name": name, "color": color}

    def get_all_tags(self) -> List[dict]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tags ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        return [{"name": row["name"], "color": row["color"]} for row in rows]

    def delete_tag(self, name: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tags WHERE name = ?", (name.lower().strip(),))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def save_setting(self, key: str, value: str) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
            """,
            (key, value),
        )
        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row["value"]
        return default

    def get_history_summary(self, days: int = 7) -> dict:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                COUNT(*) as total_sessions,
                SUM(CASE WHEN session_type = 'focus' THEN 1 ELSE 0 END) as focus_sessions,
                SUM(CASE WHEN session_type = 'focus' THEN duration_seconds ELSE 0 END) as total_focus_seconds
            FROM pomodoro_sessions
            WHERE completed_at >= date('now', ?)
            """,
            (f"-{days} days",),
        )
        totals = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*) as completed_tasks
            FROM tasks
            WHERE status = 'completed'
            AND completed_at >= date('now', ?)
            """,
            (f"-{days} days",),
        )
        tasks = cursor.fetchone()

        conn.close()

        return {
            "days": days,
            "total_sessions": totals["total_sessions"] or 0,
            "focus_sessions": totals["focus_sessions"] or 0,
            "total_focus_minutes": (totals["total_focus_seconds"] or 0) // 60,
            "completed_tasks": tasks["completed_tasks"] or 0,
        }
