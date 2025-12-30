"""Reachy Mini Pomodoro - A productivity timer app with expressive robot companionship."""

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import for ReachyMiniPomodoro to avoid import errors when dependencies missing."""
    if name == "ReachyMiniPomodoro":
        from reachy_mini_pomodoro.main import ReachyMiniPomodoro
        return ReachyMiniPomodoro
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["ReachyMiniPomodoro"]
