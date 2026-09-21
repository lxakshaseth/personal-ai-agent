"""
Backwards-compatible alias for app.voice.text_to_speech.
"""
from app.voice.text_to_speech import (
    TextToSpeechProvider as TextToSpeech,
    Pyttsx3TTSProvider as Pyttsx3TTS,
    SystemTTSProvider,
    MockTTSProvider as MockTTS,
    get_tts_provider,
)

__all__ = [
    "TextToSpeech",
    "Pyttsx3TTS",
    "SystemTTSProvider",
    "MockTTS",
    "get_tts_provider",
]
