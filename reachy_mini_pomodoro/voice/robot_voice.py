"""Robot-based voice loop for Compita.

Uses the robot's built-in microphone and speaker instead of browser audio.
This works when accessing the app over HTTP (not just HTTPS).
"""

import asyncio
import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Optional

import numpy as np
from scipy.signal import resample

from reachy_mini_pomodoro.voice.agent import (
    CompitaVoiceSession,
    SessionState,
    OPENAI_SAMPLE_RATE,
)
from reachy_mini_pomodoro.voice.wake_word import WakeWordDetector

if TYPE_CHECKING:
    from reachy_mini import ReachyMini
    from reachy_mini_pomodoro.movements import MovementManager
    from reachy_mini_pomodoro.pomodoro_timer import PomodoroTimer
    from reachy_mini_pomodoro.task_manager import TaskManager

logger = logging.getLogger(__name__)


class RobotVoiceLoop:
    """Voice loop using robot's microphone and speaker.

    Similar to the conversation app's LocalStream, but integrated with
    Compita's wake word detection and session management.
    """

    def __init__(
        self,
        robot: "ReachyMini",
        timer: "PomodoroTimer",
        task_manager: "TaskManager",
        movement_manager: Optional["MovementManager"] = None,
        openai_api_key: Optional[str] = None,
        voice: str = "coral",
    ) -> None:
        """Initialize robot voice loop.

        Args:
            robot: The ReachyMini robot instance with media access.
            timer: The Pomodoro timer instance.
            task_manager: The task manager instance.
            movement_manager: Optional movement manager for animations.
            openai_api_key: OpenAI API key.
            voice: Voice to use for responses.
        """
        self._robot = robot
        self._timer = timer
        self._task_manager = task_manager
        self._movement_manager = movement_manager
        self._api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._voice = voice

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._session: Optional[CompitaVoiceSession] = None
        self._wake_word_detector: Optional[WakeWordDetector] = None

        self._input_sample_rate: Optional[int] = None
        self._output_sample_rate: Optional[int] = None
        self._last_audio_rms: float = 0.0
        self._last_audio_max: float = 0.0

    def start(self) -> None:
        """Start the robot voice loop in a background thread."""
        if self._running:
            return

        if not self._api_key:
            logger.warning("No OpenAI API key - robot voice loop not started")
            return

        self._running = True

        def run_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run())
            except Exception as e:
                logger.error(f"Robot voice loop error: {e}")
            finally:
                loop.close()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        logger.info("Robot voice loop thread started")

    async def _run(self) -> None:
        """Main async run loop."""
        try:
            self._wake_word_detector = WakeWordDetector()
            if self._wake_word_detector._use_simple_detection:
                logger.warning(
                    "Wake word detector using simple mode (openWakeWord not installed). "
                    "Wake word detection will NOT work. Use UI button to activate."
                )
            else:
                logger.info("Wake word detector using openWakeWord - say 'hey jarvis' to activate")
        except Exception as e:
            logger.warning(f"Wake word detector not available: {e}")

        try:
            self._robot.media.start_recording()
            self._robot.media.start_playing()
            logger.info("Robot media started, waiting for initialization...")
            await asyncio.sleep(1.0)  
            self._input_sample_rate = self._robot.media.get_input_audio_samplerate()
            self._output_sample_rate = self._robot.media.get_output_audio_samplerate()
            logger.info(
                f"Robot audio initialized - input: {self._input_sample_rate}Hz, "
                f"output: {self._output_sample_rate}Hz"
            )
        except Exception as e:
            logger.error(f"Failed to start robot audio: {e}")
            self._running = False
            return

        # Create session AFTER media is ready
        self._session = CompitaVoiceSession(
            timer=self._timer,
            task_manager=self._task_manager,
            movement_manager=self._movement_manager,
            openai_api_key=self._api_key,
            voice=self._voice,
            on_audio_output=self._handle_audio_output,
            on_transcript=self._handle_transcript,
            on_state_change=self._handle_state_change,
        )
        self._session.start()
        logger.info("Compita voice session started")

        try:
            await asyncio.gather(
                self._record_loop(),
                self._session.run_timeout_checker(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self._cleanup()

    async def _record_loop(self) -> None:
        """Record audio from robot mic and process it."""
        logger.info("Robot voice record loop started")
        frame_count = 0
        none_count = 0

        while self._running:
            try:
                audio_frame = self._robot.media.get_audio_sample()

                if audio_frame is None:
                    none_count += 1
                    if none_count % 500 == 0:
                        logger.warning(f"No audio frames received ({none_count} None samples)")
                    await asyncio.sleep(0.01)
                    continue

                frame_count += 1
                if frame_count == 1:
                    logger.info(f"First audio frame received! Shape: {audio_frame.shape}, dtype: {audio_frame.dtype}")

                rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
                max_val = np.max(np.abs(audio_frame))
                self._last_audio_rms = float(rms)
                self._last_audio_max = float(max_val)

                if frame_count % 100 == 0:
                    logger.info(f"Audio frames: {frame_count}, state: {self._session.state.value if self._session else 'no session'}, rms: {rms:.6f}, max: {max_val:.6f}")

                if self._session:
                    if len(audio_frame.shape) > 1 and audio_frame.shape[1] > 1:
                        audio_mono = np.mean(audio_frame, axis=1)
                    else:
                        audio_mono = audio_frame.flatten()

                    if audio_mono.dtype in (np.float32, np.float64):
                        audio_int16 = (audio_mono * 32767).astype(np.int16)
                    else:
                        audio_int16 = audio_mono.astype(np.int16)

                    if self._input_sample_rate and self._input_sample_rate != OPENAI_SAMPLE_RATE:
                        target_len = int(
                            len(audio_int16) * OPENAI_SAMPLE_RATE / self._input_sample_rate
                        )
                        audio_resampled = resample(
                            audio_int16.astype(np.float32), target_len
                        ).astype(np.int16)
                    else:
                        audio_resampled = audio_int16

                    if (
                        self._session.state == SessionState.LISTENING
                        and self._wake_word_detector
                    ):
                        if self._wake_word_detector.process_audio(audio_resampled):
                            logger.info("Wake word detected from robot mic!")
                            await self._session.activate()

                    await self._session.process_audio(audio_resampled.tobytes())

            except Exception as e:
                if self._running:
                    logger.debug(f"Record loop error: {e}")

            await asyncio.sleep(0)  

    def _handle_audio_output(self, audio_bytes: bytes) -> None:
        """Handle audio output from Compita - play through robot speaker."""
        try:
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32767.0

            if self._output_sample_rate and self._output_sample_rate != OPENAI_SAMPLE_RATE:
                target_len = int(
                    len(audio_float) * self._output_sample_rate / OPENAI_SAMPLE_RATE
                )
                audio_resampled = resample(audio_float, target_len).astype(np.float32)
            else:
                audio_resampled = audio_float

            audio_output = audio_resampled.reshape(-1, 1)
            self._robot.media.push_audio_sample(audio_output)

        except Exception as e:
            logger.debug(f"Audio output error: {e}")

    def _handle_transcript(self, role: str, text: str) -> None:
        """Handle transcript from session."""
        logger.info(f"[Robot Voice] {role}: {text}")

    def _handle_state_change(self, state: SessionState) -> None:
        """Handle session state changes."""
        logger.info(f"[Robot Voice] State: {state.value}")

    async def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up robot voice loop...")

        if self._session:
            self._session.stop()
            self._session = None

        try:
            self._robot.media.stop_recording()
        except Exception as e:
            logger.debug(f"Error stopping recording: {e}")

        try:
            self._robot.media.stop_playing()
        except Exception as e:
            logger.debug(f"Error stopping playback: {e}")

    def stop(self) -> None:
        """Stop the robot voice loop."""
        self._running = False

        if self._session:
            self._session.stop()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

        logger.info("Robot voice loop stopped")

    def is_running(self) -> bool:
        """Check if the loop is running."""
        return self._running
