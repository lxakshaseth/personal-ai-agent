"""
Voice Activity Detection (VAD) module using WebRTC VAD with energy fallback.
Enables real-time, low-latency detection of user speech onset, ongoing speech,
and speech completion without waiting for long arbitrary silence delays.
"""
from __future__ import annotations

import collections
import logging
import time
from typing import Callable, Deque, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import webrtcvad  # type: ignore
    _HAS_WEBRTC_VAD = True
except ImportError:
    webrtcvad = None
    _HAS_WEBRTC_VAD = False


class VoiceActivityDetector:
    """
    Real-time streaming Voice Activity Detector.

    Features:
    - WebRTC VAD C-level engine (modes 0-3) for high-accuracy speech distinction.
    - Automatic 20ms frame slicing for 16kHz 16-bit mono PCM audio.
    - Energy-based fallback when webrtcvad is absent.
    - Ring buffer for speech onset capture (includes ~200ms of pre-speech audio).
    - Low-latency trailing silence debounce (e.g. 350ms - 500ms).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        aggressiveness: int = 3,
        silence_timeout_ms: int = 450,
        pre_speech_padding_ms: int = 200,
        energy_threshold: float = 0.008,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.bytes_per_sample = 2  # 16-bit
        # Bytes per frame: sample_rate * (duration_ms / 1000) * 2 bytes
        self.frame_size = int(self.sample_rate * (self.frame_duration_ms / 1000.0) * self.bytes_per_sample)
        self.silence_timeout_ms = silence_timeout_ms
        self.energy_threshold = energy_threshold

        self.vad: Optional[webrtcvad.Vad] = None
        if _HAS_WEBRTC_VAD:
            try:
                self.vad = webrtcvad.Vad(max(0, min(3, aggressiveness)))
            except Exception as e:
                logger.warning("Failed to initialize WebRTC VAD (%s); using energy fallback.", e)
                self.vad = None

        # Number of consecutive silence frames before declaring end-of-speech
        self.silence_frames_threshold = max(2, int(silence_timeout_ms / frame_duration_ms))
        
        # Ring buffer for pre-speech frames
        num_padding_frames = max(1, int(pre_speech_padding_ms / frame_duration_ms))
        self._ring_buffer: Deque[bytes] = collections.deque(maxlen=num_padding_frames)

        # Internal state
        self._buffer = bytearray()
        self._is_speaking = False
        self._speech_frames: List[bytes] = []
        self._consecutive_silence_count = 0
        self._speech_start_time: Optional[float] = None

    @property
    def is_speaking(self) -> bool:
        """True if user is actively in a spoken utterance."""
        return self._is_speaking

    def reset(self) -> None:
        """Reset detector state for a new utterance."""
        self._buffer.clear()
        self._ring_buffer.clear()
        self._speech_frames.clear()
        self._is_speaking = False
        self._consecutive_silence_count = 0
        self._speech_start_time = None

    def is_frame_speech(self, frame: bytes) -> bool:
        """Determine whether a single frame of exact size contains speech."""
        if len(frame) != self.frame_size:
            return False

        # Fast energy check: near-zero audio is immediately silence without waiting for filter decay
        import numpy as np  # type: ignore
        samples = np.frombuffer(frame, dtype=np.int16)
        amplitude = float(np.abs(samples).mean()) / 32767.0
        if amplitude < 0.002:
            return False

        if self.vad is not None:
            try:
                return self.vad.is_speech(frame, self.sample_rate)
            except Exception:
                pass

        # Energy fallback
        return amplitude >= self.energy_threshold

    def process_chunk(self, audio_chunk: bytes) -> Tuple[Optional[str], Optional[bytes]]:
        """
        Process an incoming stream of PCM bytes.

        Returns:
            Tuple of (event_type, audio_data):
            - ("speech_start", None) -> when speech begins
            - ("speech_final", full_audio_bytes) -> when speech completes with trailing silence
            - (None, None) -> intermediate or silent state
        """
        if not audio_chunk:
            return None, None

        self._buffer.extend(audio_chunk)
        event_to_return: Optional[str] = None
        completed_audio: Optional[bytes] = None

        while len(self._buffer) >= self.frame_size:
            frame = bytes(self._buffer[:self.frame_size])
            del self._buffer[:self.frame_size]

            frame_is_speech = self.is_frame_speech(frame)

            if not self._is_speaking:
                self._ring_buffer.append(frame)
                if frame_is_speech:
                    # Speech onset detected!
                    self._is_speaking = True
                    self._speech_start_time = time.time()
                    self._speech_frames = list(self._ring_buffer)
                    self._consecutive_silence_count = 0
                    event_to_return = "speech_start"
            else:
                # We are currently in speech
                self._speech_frames.append(frame)
                if frame_is_speech:
                    self._consecutive_silence_count = 0
                else:
                    self._consecutive_silence_count += 1
                    if self._consecutive_silence_count >= self.silence_frames_threshold:
                        # User stopped speaking!
                        self._is_speaking = False
                        event_to_return = "speech_final"
                        completed_audio = b"".join(self._speech_frames)
                        self._speech_frames.clear()
                        self._ring_buffer.clear()
                        break

        return event_to_return, completed_audio
