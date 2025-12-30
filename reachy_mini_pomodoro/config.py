"""Configuration settings for the Pomodoro app."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TimerState(Enum):
    """Possible states of the Pomodoro timer."""
    IDLE = "idle"
    FOCUS = "focus"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"
    PAUSED = "paused"


@dataclass
class PomodoroSettings:
    """Configurable Pomodoro timer settings."""

    # Timer durations in seconds
    focus_duration: int = 25 * 60  # 25 minutes
    short_break_duration: int = 5 * 60  # 5 minutes
    long_break_duration: int = 15 * 60  # 15 minutes

    # Long break occurs after this many pomodoros
    pomodoros_until_long_break: int = 4

    # Robot behavior settings
    focus_reminder_interval: int = 5 * 60  # Remind every 5 minutes during focus
    enable_sounds: bool = True
    enable_movements: bool = True


@dataclass
class BreakActivity:
    """A suggested activity during breaks."""
    name: str
    description: str
    duration_seconds: int
    robot_demo: bool = False  # Whether Reachy can demonstrate this


# Default break activities
DEFAULT_BREAK_ACTIVITIES: List[BreakActivity] = [
    BreakActivity(
        name="Deep Breathing",
        description="Take 5 deep breaths. Inhale for 4 seconds, hold for 4, exhale for 4.",
        duration_seconds=60,
        robot_demo=True
    ),
    BreakActivity(
        name="Neck Stretches",
        description="Gently tilt your head left, right, forward, and back.",
        duration_seconds=30,
        robot_demo=True
    ),
    BreakActivity(
        name="Eye Rest",
        description="Look at something 20 feet away for 20 seconds (20-20-20 rule).",
        duration_seconds=20,
        robot_demo=False
    ),
    BreakActivity(
        name="Shoulder Rolls",
        description="Roll your shoulders forward 5 times, then backward 5 times.",
        duration_seconds=30,
        robot_demo=True
    ),
    BreakActivity(
        name="Stand & Stretch",
        description="Stand up, reach for the sky, then touch your toes.",
        duration_seconds=45,
        robot_demo=False
    ),
    BreakActivity(
        name="Hydration Break",
        description="Drink a glass of water. Stay hydrated!",
        duration_seconds=30,
        robot_demo=False
    ),
    BreakActivity(
        name="Quick Walk",
        description="Take a short walk around your space.",
        duration_seconds=120,
        robot_demo=False
    ),
    BreakActivity(
        name="Wrist Circles",
        description="Rotate your wrists clockwise and counter-clockwise.",
        duration_seconds=30,
        robot_demo=True
    ),
]


# App configuration
APP_HOST = "0.0.0.0"
APP_PORT = 8042
CUSTOM_APP_URL = f"http://{APP_HOST}:{APP_PORT}"

# Update frequency for the main control loop (Hz)
CONTROL_LOOP_FREQUENCY = 50  # 50 Hz = 20ms per iteration


@dataclass
class CompitaSettings:
    """Configuration for Compita voice assistant.

    Compita uses OpenAI's Realtime API for voice interaction.
    Set OPENAI_API_KEY environment variable or pass it directly.
    """

    enabled: bool = True

    # OpenAI settings
    openai_api_key: Optional[str] = None  # Falls back to OPENAI_API_KEY env var
    model: str = "gpt-4o-realtime-preview"
    voice: str = "coral"  # Options: alloy, echo, fable, onyx, nova, shimmer, coral


# Default Compita settings
DEFAULT_COMPITA_SETTINGS = CompitaSettings()
