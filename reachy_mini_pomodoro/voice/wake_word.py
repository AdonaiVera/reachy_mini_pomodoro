"""Wake word detection for Compita voice assistant.

Uses openWakeWord for detecting the activation phrase.
Falls back to simple speech recognition if openWakeWord is not available.
"""

import logging
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000  # openWakeWord uses 16kHz


class WakeWordDetector:
    """Detects wake word 'Compita' in audio stream."""

    def __init__(
        self,
        on_wake_word: Optional[Callable[[], None]] = None,
        threshold: float = 0.5,
    ) -> None:
        """Initialize wake word detector.

        Args:
            on_wake_word: Callback when wake word is detected.
            threshold: Detection threshold (0-1).
        """
        self.on_wake_word = on_wake_word
        self.threshold = threshold
        self._model = None
        self._enabled = True
        self._buffer = np.array([], dtype=np.int16)
        self._use_simple_detection = False

        self._init_detector()

    def _init_detector(self) -> None:
        """Initialize the wake word detection model."""
        try:
            import openwakeword
            from openwakeword.model import Model

            # Use a pre-trained model - "hey_jarvis" is similar phonetically
            # For production, train a custom "compita" model
            self._model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
            )
            logger.info("openWakeWord initialized with hey_jarvis model")
            logger.info("Note: For production, train a custom 'compita' model")

        except ImportError:
            logger.warning(
                "openWakeWord not installed. Using simple keyword detection. "
                "Install with: pip install openwakeword"
            )
            self._use_simple_detection = True

        except Exception as e:
            logger.error(f"Failed to initialize openWakeWord: {e}")
            self._use_simple_detection = True

    def process_audio(self, audio: np.ndarray, sample_rate: int = 16000) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio: Audio samples (int16 or float32).
            sample_rate: Sample rate of audio.

        Returns:
            True if wake word was detected.
        """
        if not self._enabled:
            return False

        # Convert to int16 if needed
        if audio.dtype == np.float32 or audio.dtype == np.float64:
            audio = (audio * 32767).astype(np.int16)

        # Resample to 16kHz if needed
        if sample_rate != SAMPLE_RATE:
            from scipy.signal import resample
            target_len = int(len(audio) * SAMPLE_RATE / sample_rate)
            audio = resample(audio.astype(np.float32), target_len).astype(np.int16)

        if self._use_simple_detection:
            return self._simple_detection(audio)

        return self._oww_detection(audio)

    def _oww_detection(self, audio: np.ndarray) -> bool:
        """Use openWakeWord for detection."""
        if not self._model:
            return False

        # Add to buffer
        self._buffer = np.concatenate([self._buffer, audio])

        # Process in chunks of 1280 samples (80ms at 16kHz)
        chunk_size = 1280
        detected = False

        while len(self._buffer) >= chunk_size:
            chunk = self._buffer[:chunk_size]
            self._buffer = self._buffer[chunk_size:]

            # Run prediction
            prediction = self._model.predict(chunk)

            # Check all models for detection
            for model_name, score in prediction.items():
                if score > self.threshold:
                    logger.info(f"Wake word detected! (model: {model_name}, score: {score:.2f})")
                    detected = True
                    if self.on_wake_word:
                        self.on_wake_word()
                    break

        return detected

    def _simple_detection(self, audio: np.ndarray) -> bool:
        """Simple detection - always return False, let OpenAI handle it.

        When openWakeWord is not available, we rely on the user
        starting their sentence with 'Compita' and OpenAI's VAD.
        """
        # For simple mode, we don't do local detection
        # The OpenAI Realtime API will handle speech and we check
        # the transcript for "Compita" mentions
        return False

    def enable(self) -> None:
        """Enable wake word detection."""
        self._enabled = True
        self._buffer = np.array([], dtype=np.int16)

    def disable(self) -> None:
        """Disable wake word detection."""
        self._enabled = False

    def reset(self) -> None:
        """Reset the detector state."""
        self._buffer = np.array([], dtype=np.int16)
        if self._model:
            self._model.reset()
