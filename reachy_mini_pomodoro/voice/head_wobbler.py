"""Head wobbler - converts audio output into head movement offsets.

Based on the Reachy Mini conversation app's implementation.
Provides realistic talking animation by analyzing audio and generating
synchronized head movements.
"""

import time
import queue
import base64
import logging
import threading
from typing import Tuple, Optional
from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from reachy_mini_pomodoro.voice.speech_tapper import HOP_MS, SwayRollRT


SAMPLE_RATE = 24000 
MOVEMENT_LATENCY_S = 0.08  
logger = logging.getLogger(__name__)


class HeadWobbler:
    """Converts audio deltas (base64 or raw bytes) into head movement offsets.

    This class processes audio output from the voice assistant and generates
    realistic head movements synchronized with the speech.
    """

    def __init__(
        self,
        set_speech_offsets: Callable[[Tuple[float, float, float, float, float, float]], None],
    ) -> None:
        """Initialize the head wobbler.

        Args:
            set_speech_offsets: Callback to apply movement offsets.
                Tuple format: (x, y, z, roll, pitch, yaw) in meters/radians.
        """
        self._apply_offsets = set_speech_offsets
        self.audio_queue: "queue.Queue[Tuple[int, int, NDArray[np.int16]]]" = queue.Queue()
        self.sway = SwayRollRT()

        self._state_lock = threading.Lock()
        self._sway_lock = threading.Lock()
        self._generation = 0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def feed(self, audio_data: bytes | str) -> None:
        """Thread-safe: push audio into the consumer queue.

        Args:
            audio_data: Either base64-encoded string or raw bytes of int16 PCM audio.
        """
        if isinstance(audio_data, str):
            buf = np.frombuffer(base64.b64decode(audio_data), dtype=np.int16).reshape(1, -1)
        else:
            buf = np.frombuffer(audio_data, dtype=np.int16).reshape(1, -1)

        with self._state_lock:
            generation = self._generation
        self.audio_queue.put((generation, SAMPLE_RATE, buf))

    def start(self) -> None:
        """Start the head wobbler loop in a thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._working_loop, daemon=True)
        self._thread.start()
        logger.debug("Head wobbler started")

    def stop(self) -> None:
        """Stop the head wobbler loop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.debug("Head wobbler stopped")

    def _working_loop(self) -> None:
        """Convert audio deltas into head movement offsets."""
        hop_dt = HOP_MS / 1000.0

        while not self._stop_event.is_set():
            queue_ref = self.audio_queue
            try:
                chunk_generation, sr, chunk = queue_ref.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                with self._state_lock:
                    current_generation = self._generation
                if chunk_generation != current_generation:
                    continue

                pcm = np.asarray(chunk).squeeze(0)
                with self._sway_lock:
                    results = self.sway.feed(pcm, sr)

                for r in results:
                    with self._state_lock:
                        if self._generation != current_generation:
                            break

                    offsets = (
                        r["x_mm"] / 1000.0,
                        r["y_mm"] / 1000.0,
                        r["z_mm"] / 1000.0,
                        r["roll_rad"],
                        r["pitch_rad"],
                        r["yaw_rad"],
                    )
                    self._apply_offsets(offsets)
                    time.sleep(hop_dt)
            finally:
                queue_ref.task_done()

    def reset(self) -> None:
        """Reset the internal state for a new conversation turn."""
        with self._state_lock:
            self._generation += 1

        while True:
            try:
                _, _, _ = self.audio_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.audio_queue.task_done()

        with self._sway_lock:
            self.sway.reset()

        self._apply_offsets((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

        logger.debug("Head wobbler reset")
