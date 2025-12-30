"""Pomodoro timer state machine."""

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, List

from reachy_mini_pomodoro.config import (
    BreakActivity,
    DEFAULT_BREAK_ACTIVITIES,
    PomodoroSettings,
    TimerState,
)


@dataclass
class TimerEvent:
    """An event emitted by the timer."""
    event_type: str
    data: dict


class PomodoroTimer:
    """State machine for the Pomodoro timer."""

    def __init__(self, settings: Optional[PomodoroSettings] = None) -> None:
        self.settings = settings or PomodoroSettings()
        self.state = TimerState.IDLE
        self.previous_state = TimerState.IDLE  # For pause/resume

        # Timer tracking
        self.time_remaining: int = 0  # Seconds remaining
        self.session_start_time: float = 0
        self.pause_time: float = 0

        # Pomodoro counting
        self.pomodoros_in_cycle: int = 0  # Count towards long break
        self.total_pomodoros: int = 0

        # Break activity
        self.current_break_activity: Optional[BreakActivity] = None

        # Event callbacks
        self._event_listeners: List[Callable[[TimerEvent], None]] = []

        # Last reminder time (for focus reminders)
        self._last_reminder_time: float = 0

    def add_event_listener(self, callback: Callable[[TimerEvent], None]) -> None:
        """Add a listener for timer events."""
        self._event_listeners.append(callback)

    def _emit_event(self, event_type: str, data: Optional[dict] = None) -> None:
        """Emit an event to all listeners."""
        event = TimerEvent(event_type=event_type, data=data or {})
        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"Error in event listener: {e}")

    def start_focus(self) -> bool:
        """Start a focus session."""
        if self.state in (TimerState.IDLE, TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            self.state = TimerState.FOCUS
            self.time_remaining = self.settings.focus_duration
            self.session_start_time = time.time()
            self._last_reminder_time = time.time()
            self._emit_event("focus_started", {
                "duration": self.settings.focus_duration,
                "pomodoro_number": self.total_pomodoros + 1,
            })
            return True
        return False

    def start_break(self, force_long: bool = False) -> bool:
        """Start a break session."""
        if self.state == TimerState.FOCUS:
            # Determine break type
            self.pomodoros_in_cycle += 1
            self.total_pomodoros += 1

            if force_long or self.pomodoros_in_cycle >= self.settings.pomodoros_until_long_break:
                self.state = TimerState.LONG_BREAK
                self.time_remaining = self.settings.long_break_duration
                self.pomodoros_in_cycle = 0
                break_type = "long"
            else:
                self.state = TimerState.SHORT_BREAK
                self.time_remaining = self.settings.short_break_duration
                break_type = "short"

            self.session_start_time = time.time()

            # Select a random break activity
            self.current_break_activity = random.choice(DEFAULT_BREAK_ACTIVITIES)

            self._emit_event("break_started", {
                "break_type": break_type,
                "duration": self.time_remaining,
                "activity": {
                    "name": self.current_break_activity.name,
                    "description": self.current_break_activity.description,
                    "robot_demo": self.current_break_activity.robot_demo,
                } if self.current_break_activity else None,
                "pomodoros_completed": self.total_pomodoros,
            })
            return True
        return False

    def pause(self) -> bool:
        """Pause the timer."""
        if self.state in (TimerState.FOCUS, TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            self.previous_state = self.state
            self.pause_time = time.time()
            self.state = TimerState.PAUSED
            self._emit_event("timer_paused", {
                "time_remaining": self.time_remaining,
                "previous_state": self.previous_state.value,
            })
            return True
        return False

    def resume(self) -> bool:
        """Resume the timer from pause."""
        if self.state == TimerState.PAUSED:
            # Adjust session start time to account for pause
            pause_duration = time.time() - self.pause_time
            self.session_start_time += pause_duration
            self.state = self.previous_state
            self._emit_event("timer_resumed", {
                "state": self.state.value,
                "time_remaining": self.time_remaining,
            })
            return True
        return False

    def stop(self) -> bool:
        """Stop the timer and return to idle."""
        if self.state != TimerState.IDLE:
            previous_state = self.state
            self.state = TimerState.IDLE
            self.time_remaining = 0
            self.current_break_activity = None
            self._emit_event("timer_stopped", {
                "previous_state": previous_state.value,
            })
            return True
        return False

    def skip(self) -> bool:
        """Skip the current session."""
        if self.state == TimerState.FOCUS:
            # Skip focus = start break
            self._emit_event("focus_skipped", {})
            return self.start_break()
        elif self.state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            # Skip break = start focus
            self.state = TimerState.IDLE
            self._emit_event("break_skipped", {})
            return self.start_focus()
        return False

    def update(self) -> None:
        """Update the timer. Should be called regularly (e.g., every second)."""
        if self.state == TimerState.PAUSED:
            return

        if self.state in (TimerState.FOCUS, TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            elapsed = time.time() - self.session_start_time
            duration = self._get_current_duration()
            self.time_remaining = max(0, int(duration - elapsed))

            # Check for focus reminders
            if self.state == TimerState.FOCUS:
                time_since_reminder = time.time() - self._last_reminder_time
                if time_since_reminder >= self.settings.focus_reminder_interval:
                    self._last_reminder_time = time.time()
                    self._emit_event("focus_reminder", {
                        "time_remaining": self.time_remaining,
                        "minutes_left": self.time_remaining // 60,
                    })

            # Check if timer completed
            if self.time_remaining <= 0:
                self._handle_timer_complete()

    def _get_current_duration(self) -> int:
        """Get the duration for the current state."""
        if self.state == TimerState.FOCUS:
            return self.settings.focus_duration
        elif self.state == TimerState.SHORT_BREAK:
            return self.settings.short_break_duration
        elif self.state == TimerState.LONG_BREAK:
            return self.settings.long_break_duration
        return 0

    def _handle_timer_complete(self) -> None:
        """Handle timer completion."""
        if self.state == TimerState.FOCUS:
            self._emit_event("focus_completed", {
                "pomodoro_number": self.total_pomodoros + 1,
            })
            self.start_break()
        elif self.state in (TimerState.SHORT_BREAK, TimerState.LONG_BREAK):
            self._emit_event("break_completed", {
                "break_type": "long" if self.state == TimerState.LONG_BREAK else "short",
            })
            self.state = TimerState.IDLE
            self.current_break_activity = None

    def get_status(self) -> dict:
        """Get the current timer status."""
        return {
            "state": self.state.value,
            "time_remaining": self.time_remaining,
            "time_remaining_formatted": self._format_time(self.time_remaining),
            "pomodoros_in_cycle": self.pomodoros_in_cycle,
            "total_pomodoros": self.total_pomodoros,
            "pomodoros_until_long_break": self.settings.pomodoros_until_long_break - self.pomodoros_in_cycle,
            "current_break_activity": {
                "name": self.current_break_activity.name,
                "description": self.current_break_activity.description,
                "robot_demo": self.current_break_activity.robot_demo,
            } if self.current_break_activity else None,
            "settings": {
                "focus_duration": self.settings.focus_duration,
                "short_break_duration": self.settings.short_break_duration,
                "long_break_duration": self.settings.long_break_duration,
                "pomodoros_until_long_break": self.settings.pomodoros_until_long_break,
            }
        }

    def update_settings(self, focus_duration: Optional[int] = None,
                        short_break_duration: Optional[int] = None,
                        long_break_duration: Optional[int] = None,
                        pomodoros_until_long_break: Optional[int] = None) -> None:
        """Update timer settings."""
        if focus_duration is not None:
            self.settings.focus_duration = max(60, min(focus_duration, 60 * 60))  # 1-60 min
        if short_break_duration is not None:
            self.settings.short_break_duration = max(60, min(short_break_duration, 30 * 60))  # 1-30 min
        if long_break_duration is not None:
            self.settings.long_break_duration = max(60, min(long_break_duration, 60 * 60))  # 1-60 min
        if pomodoros_until_long_break is not None:
            self.settings.pomodoros_until_long_break = max(2, min(pomodoros_until_long_break, 10))

    @staticmethod
    def _format_time(seconds: int) -> str:
        """Format seconds as MM:SS."""
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"
