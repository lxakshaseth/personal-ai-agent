"""
Voice interface package.

Provides modular speech-to-text, text-to-speech, microphone capture,
and the end-to-end VoiceController.
"""
from app.voice.microphone import (
    MicrophoneRecorder,
    MockMicrophoneRecorder,
    is_microphone_available,
)
from app.voice.schemas import (
    AudioData,
    AudioFormat,
    SpeechRecognitionResult,
    VoiceCommandResult,
    VoiceMode,
    WakeWordCheckResult,
)
from app.voice.speech_to_text import (
    GroqSTTProvider,
    LocalWhisperSTTProvider,
    MockSTTProvider,
    OpenAISTTProvider,
    SpeechToTextProvider,
    get_stt_provider,
)
from app.voice.text_to_speech import (
    MockTTSProvider,
    Pyttsx3TTSProvider,
    SystemTTSProvider,
    TextToSpeechProvider,
    get_tts_provider,
)


def __getattr__(name: str):
    if name == "VoiceController":
        from app.voice.voice_controller import VoiceController
        return VoiceController
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [

    # Interfaces
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    # Providers & Factories
    "GroqSTTProvider",
    "OpenAISTTProvider",
    "LocalWhisperSTTProvider",
    "MockSTTProvider",
    "get_stt_provider",
    "SystemTTSProvider",
    "Pyttsx3TTSProvider",
    "MockTTSProvider",
    "get_tts_provider",
    # Microphone
    "MicrophoneRecorder",
    "MockMicrophoneRecorder",
    "is_microphone_available",
    # Controller
    "VoiceController",
    # Schemas
    "AudioData",
    "AudioFormat",
    "SpeechRecognitionResult",
    "VoiceCommandResult",
    "VoiceMode",
    "WakeWordCheckResult",
]
