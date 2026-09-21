"""
Pydantic schemas and dataclasses for the voice interface.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class VoiceMode(str, Enum):
    """Current state of the voice interface."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class AudioFormat(str, Enum):
    WAV = "wav"
    PCM = "pcm"
    MP3 = "mp3"


class AudioData(BaseModel):
    """Raw or formatted audio capture container."""
    audio_bytes: bytes
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit PCM
    format: AudioFormat = AudioFormat.WAV
    duration_seconds: float = 0.0


class SpeechRecognitionResult(BaseModel):
    """Result returned by SpeechToTextProvider."""
    text: str
    confidence: Optional[float] = None
    language: Optional[str] = None
    duration_seconds: Optional[float] = None


class WakeWordCheckResult(BaseModel):
    """Result of checking an input phrase for wake word presence."""
    detected: bool
    wake_word: Optional[str] = None
    command_text: str  # Cleaned command with wake word stripped


class VoiceCommandResult(BaseModel):
    """End-to-end outcome of a voice interaction turn."""
    raw_transcript: str
    command_text: str
    wake_word_detected: bool = False
    success: bool = True
    spoken_response: Optional[str] = None
    agent_output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
