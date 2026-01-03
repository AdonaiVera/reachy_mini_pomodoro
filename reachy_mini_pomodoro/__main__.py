"""Entry point for running the Pomodoro app directly."""

import argparse

from reachy_mini_pomodoro.main import ReachyMiniPomodoro


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reachy Mini Pomodoro App")
    parser.add_argument(
        "--wireless",
        action="store_true",
        help="Connect to wireless Reachy Mini (not localhost)",
    )
    args = parser.parse_args()

    # For wireless Reachy Mini, use localhost_only=False
    app = ReachyMiniPomodoro(localhost_only=not args.wireless)
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
