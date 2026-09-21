"""
Microphone abstraction and recording module.

Provides:
  - MicrophoneRecorder: audio capture using sounddevice (or mock/fallback)
  - Detection of hardware availability
  - Phrase-based recording (does not continuously record unless requested)
  - Graceful handling of device absence, timeout, and silence
"""
from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import Optional

from app.utils.exceptions import (
    MicrophoneError,
    MicrophoneUnavailableError,
    NoSpeechDetectedError,
    VoiceTimeoutError,
)
from app.voice.schemas import AudioData, AudioFormat

logger = logging.getLogger(__name__)


def is_microphone_available() -> bool:
    """Check if an audio input device is available on the system."""
    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
        return len(input_devices) > 0
    except Exception as exc:
        logger.debug("Microphone availability check failed: %s", exc)
        return False


class MicrophoneRecorder:
    """
    Microphone recording helper.

    Records on-demand phrases (never records continuously in the background
    unless explicitly told to do so).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        sample_width: int = 2,  # 16-bit
        energy_threshold: float = 0.01,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.energy_threshold = energy_threshold

    def is_available(self) -> bool:
        return is_microphone_available()

    def has_microphone(self) -> bool:
        """Alias for is_available()."""
        return is_microphone_available()

    async def record_phrase(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 7.0,
    ) -> AudioData:
        """
        Record a single spoken phrase from the microphone with VAD early-stop.

        Uses energy-based Voice Activity Detection: records in 100 ms chunks and
        stops 0.8 s after speech energy drops below threshold, so short commands
        (e.g. "open YouTube") finish in ~2-3 s instead of waiting the full limit.

        Args:
            timeout: Maximum seconds to wait for speech to start.
            phrase_time_limit: Hard cap on recording duration (seconds).

        Returns:
            AudioData containing WAV formatted bytes.

        Raises:
            MicrophoneUnavailableError: If no mic hardware is present.
            NoSpeechDetectedError: If only silence is recorded.
            VoiceTimeoutError: If recording times out.
        """
        if not self.is_available():
            raise MicrophoneUnavailableError(
                "No microphone input device was detected on this computer. "
                "Please connect a microphone or use keyboard text mode."
            )

        try:
            import numpy as np  # type: ignore
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise MicrophoneUnavailableError(
                "Audio recording packages (sounddevice, numpy) are not installed. "
                "Install with: pip install sounddevice numpy"
            ) from exc

        logger.info("Listening for phrase (max: %.1fs, timeout: %.1fs)...", phrase_time_limit, timeout)

        # Run recording in a thread pool to keep asyncio loop unblocked
        loop = asyncio.get_running_loop()

        def _record_sync() -> bytes:
            """
            Chunk-based recording with energy VAD.
            Collects 100 ms frames; stops when:
              - 0.8 s of silence after initial speech, OR
              - phrase_time_limit reached
            """
            chunk_size = int(0.1 * self.sample_rate)   # 100 ms per chunk
            silence_limit_chunks = 8                    # 0.8 s of trailing silence
            max_chunks = int(phrase_time_limit / 0.1)
            speech_started = False
            silence_count = 0
            frames: list[np.ndarray] = []

            try:
                for _ in range(max_chunks):
                    chunk = sd.rec(
                        chunk_size,
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        dtype="int16",
                        blocking=True,
                    )
                    frames.append(chunk.copy())

                    amplitude = np.abs(chunk).mean() / 32767.0
                    if amplitude >= self.energy_threshold:
                        speech_started = True
                        silence_count = 0
                    elif speech_started:
                        silence_count += 1
                        if silence_count >= silence_limit_chunks:
                            logger.debug("VAD early-stop after %.1f s", len(frames) * 0.1)
                            break
            except Exception as e:
                raise MicrophoneError(f"Failed to record audio from microphone: {e}") from e

            if not frames:
                raise NoSpeechDetectedError("No audio was captured.")

            recording = np.concatenate(frames, axis=0)
            actual_energy = np.abs(recording).mean() / 32767.0
            logger.debug(
                "Recorded %.2f s, energy=%.4f (threshold=%.4f), speech_started=%s",
                len(frames) * 0.1, actual_energy, self.energy_threshold, speech_started,
            )

            if not speech_started or actual_energy < self.energy_threshold:
                raise NoSpeechDetectedError("No speech detected (audio was silent).")

            # Convert to WAV bytes
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.sample_width)
                wf.setframerate(self.sample_rate)
                wf.writeframes(recording.tobytes())
            return buf.getvalue()

        try:
            audio_bytes = await loop.run_in_executor(None, _record_sync)
        except (MicrophoneError, NoSpeechDetectedError):
            raise
        except Exception as exc:
            raise MicrophoneError(f"Microphone recording failed: {exc}") from exc

        return AudioData(
            audio_bytes=audio_bytes,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
            format=AudioFormat.WAV,
            duration_seconds=phrase_time_limit,
        )


class MockMicrophoneRecorder(MicrophoneRecorder):
    """
    Deterministic mock microphone for unit testing and CI.
    Accepts pre-configured audio or raises programmed exceptions.
    """

    def __init__(
        self,
        audio_data: Optional[AudioData] = None,
        exception_to_raise: Optional[Exception] = None,
    ) -> None:
        super().__init__()
        self._audio_data = audio_data or AudioData(
            audio_bytes=b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80>\x00\x00\x00}\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00",
            duration_seconds=1.0,
        )
        self._exception_to_raise = exception_to_raise
        self._available = True

    def set_available(self, available: bool) -> None:
        self._available = available

    def is_available(self) -> bool:
        return self._available

    async def record_phrase(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 10.0,
    ) -> AudioData:
        if not self._available:
            raise MicrophoneUnavailableError("Mock microphone unavailable.")
        if self._exception_to_raise:
            raise self._exception_to_raise
        return self._audio_data
