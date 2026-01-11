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
    parser.add_argument(
        "--no-robot-audio",
        action="store_true",
        help="Disable robot microphone/speaker (use browser audio instead)",
    )
    args = parser.parse_args()

    media_backend = "no_media" if args.no_robot_audio else None

    app = ReachyMiniPomodoro(
        localhost_only=not args.wireless,
        media_backend_override=media_backend,
    )
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
