"""
Backwards-compatible alias for app.voice.speech_to_text.
"""
from app.voice.speech_to_text import (
    SpeechToTextProvider as SpeechToText,
    LocalWhisperSTTProvider as WhisperSTT,
    MockSTTProvider as MockSTT,
    GroqSTTProvider,
    OpenAISTTProvider,
    get_stt_provider,
)

__all__ = [
    "SpeechToText",
    "WhisperSTT",
    "MockSTT",
    "GroqSTTProvider",
    "OpenAISTTProvider",
    "get_stt_provider",
]
