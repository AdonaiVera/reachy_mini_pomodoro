"""Wake word detection for Compita voice assistant.

Wake word detection is handled via transcript checking in CompitaVoiceSession.
This module provides a simple stub for compatibility.
"""

import logging
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


class WakeWordDetector:
    """Stub wake word detector - actual detection is via transcript checking."""

    def __init__(
        self,
        on_wake_word: Optional[Callable[[], None]] = None,
        threshold: float = 0.5,
    ) -> None:
        """Initialize wake word detector.

        Args:
            on_wake_word: Callback when wake word is detected.
            threshold: Detection threshold (unused).
        """
        self.on_wake_word = on_wake_word
        self.threshold = threshold
        self._enabled = True
        self._use_simple_detection = True

        logger.info("Wake word detection via transcript checking (say 'Compita')")

    def process_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> bool:
        """Process audio - returns False, detection is via transcript.

        Args:
            audio: Audio samples (unused).
            sample_rate: Sample rate (unused).

        Returns:
            Always False - wake word is detected via transcript checking.
        """
        return False

    def enable(self) -> None:
        """Enable wake word detection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable wake word detection."""
        self._enabled = False

    def reset(self) -> None:
        """Reset the detector state."""
        pass
