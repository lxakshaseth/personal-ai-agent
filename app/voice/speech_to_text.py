"""
Speech-to-Text provider abstraction and implementations.

Provides:
  - SpeechToTextProvider (ABC)
  - GroqSTTProvider (uses Groq Cloud Whisper API via GROQ_API_KEY)
  - OpenAISTTProvider (uses OpenAI Whisper API)
  - LocalWhisperSTTProvider (offline faster-whisper)
  - MockSTTProvider (deterministic mock for unit tests)
  - get_stt_provider() factory
"""
from __future__ import annotations

import abc
import io
import logging
from pathlib import Path
from typing import BinaryIO, Optional, Union

from app.config.settings import get_settings
from app.utils.exceptions import SpeechRecognitionError
from app.voice.schemas import AudioData, SpeechRecognitionResult

logger = logging.getLogger(__name__)


class SpeechToTextProvider(abc.ABC):
    """Abstract interface for all speech-to-text providers."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the STT provider."""
        ...

    @abc.abstractmethod
    async def transcribe(
        self,
        audio: Union[AudioData, bytes, Path, str, BinaryIO],
        *,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        """
        Transcribe audio input into text.

        Args:
            audio: AudioData container, raw audio bytes, file path, or file-like object.
            language: Optional ISO language code (e.g. 'en').
            prompt: Optional context prompt to improve transcription accuracy.

        Returns:
            SpeechRecognitionResult with text transcript and metadata.

        Raises:
            SpeechRecognitionError on transcription failure.
        """
        ...


class GroqSTTProvider(SpeechToTextProvider):
    """
    Speech-to-text provider using Groq's high-speed Whisper Cloud API.
    Reuses the configured GROQ_API_KEY from environment variables.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3-turbo",
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.groq_api_key
        self._model = model
        self._client = None

    @property
    def provider_name(self) -> str:
        return "groq"

    def _get_client(self):
        if self._client is None:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def transcribe(
        self,
        audio: Union[AudioData, bytes, Path, str, BinaryIO],
        *,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        client = self._get_client()

        # Normalise audio input to a file tuple suitable for Groq SDK
        file_tuple = None
        if isinstance(audio, AudioData):
            file_tuple = ("audio.wav", audio.audio_bytes, "audio/wav")
        elif isinstance(audio, bytes):
            file_tuple = ("audio.wav", audio, "audio/wav")
        elif isinstance(audio, (str, Path)):
            path = Path(audio)
            if not path.exists():
                raise SpeechRecognitionError(f"Audio file not found: {path}")
            file_tuple = (path.name, path.read_bytes(), "audio/wav")
        elif hasattr(audio, "read"):
            file_tuple = ("audio.wav", audio.read(), "audio/wav")
        else:
            raise SpeechRecognitionError(f"Unsupported audio type: {type(audio)}")

        try:
            kwargs = {"model": self._model, "file": file_tuple}
            if language:
                kwargs["language"] = language
            if prompt:
                kwargs["prompt"] = prompt

            transcription = await client.audio.transcriptions.create(**kwargs)
            text = transcription.text.strip() if hasattr(transcription, "text") else str(transcription).strip()
            return SpeechRecognitionResult(text=text)
        except Exception as exc:
            logger.error("Groq STT transcription failed: %s", exc)
            raise SpeechRecognitionError(f"Groq STT failed: {exc}") from exc


class OpenAISTTProvider(SpeechToTextProvider):
    """Speech-to-text provider using OpenAI Whisper API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1") -> None:
        import os
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    async def transcribe(
        self,
        audio: Union[AudioData, bytes, Path, str, BinaryIO],
        *,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        if not self._api_key:
            raise SpeechRecognitionError("OPENAI_API_KEY is not configured.")
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self._api_key)
            if isinstance(audio, AudioData):
                file_tuple = ("audio.wav", audio.audio_bytes, "audio/wav")
            elif isinstance(audio, bytes):
                file_tuple = ("audio.wav", audio, "audio/wav")
            elif isinstance(audio, (str, Path)):
                file_tuple = (Path(audio).name, Path(audio).read_bytes(), "audio/wav")
            else:
                file_tuple = ("audio.wav", audio.read(), "audio/wav")

            transcription = await client.audio.transcriptions.create(
                model=self._model,
                file=file_tuple,
                language=language or "en",
            )
            return SpeechRecognitionResult(text=transcription.text.strip())
        except Exception as exc:
            raise SpeechRecognitionError(f"OpenAI STT failed: {exc}") from exc


class LocalWhisperSTTProvider(SpeechToTextProvider):
    """Speech-to-text provider using local faster-whisper."""

    def __init__(self, model_size: str = "base") -> None:
        self._model_size = model_size
        self._model = None

    @property
    def provider_name(self) -> str:
        return "whisper"

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            except ImportError as exc:
                raise SpeechRecognitionError(
                    "faster-whisper is not installed. Install with: pip install faster-whisper"
                ) from exc

    async def transcribe(
        self,
        audio: Union[AudioData, bytes, Path, str, BinaryIO],
        *,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        import tempfile
        self._load_model()

        # Write to temporary file for faster-whisper
        if isinstance(audio, (str, Path)) and Path(audio).exists():
            tmp_path = str(audio)
            cleanup = False
        else:
            raw_bytes = audio.audio_bytes if isinstance(audio, AudioData) else (
                audio if isinstance(audio, bytes) else audio.read()
            )
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            cleanup = True

        try:
            segments, _ = self._model.transcribe(tmp_path, beam_size=5, language=language)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return SpeechRecognitionResult(text=text)
        except Exception as exc:
            raise SpeechRecognitionError(f"Local Whisper transcription failed: {exc}") from exc
        finally:
            if cleanup:
                Path(tmp_path).unlink(missing_ok=True)


class MockSTTProvider(SpeechToTextProvider):
    """Deterministic STT provider for unit tests and CI."""

    def __init__(self, fixed_text: str = "open YouTube") -> None:
        self.fixed_text = fixed_text
        self._call_count = 0
        self._queue: list[str] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    def queue_transcript(self, text: str) -> None:
        """Queue a transcript to be returned on the next call."""
        self._queue.append(text)

    async def transcribe(
        self,
        audio: Union[AudioData, bytes, Path, str, BinaryIO],
        *,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> SpeechRecognitionResult:
        self._call_count += 1
        if self._queue:
            text = self._queue.pop(0)
        else:
            text = self.fixed_text
        return SpeechRecognitionResult(text=text, confidence=1.0)


def get_stt_provider(provider_name: Optional[str] = None) -> SpeechToTextProvider:
    """Factory to obtain the configured SpeechToTextProvider."""
    name = (provider_name or get_settings().stt_provider).strip().lower()

    if name in ("groq", "groq_whisper", "groq-whisper"):
        return GroqSTTProvider()
    elif name in ("openai", "openai_whisper"):
        return OpenAISTTProvider()
    elif name in ("whisper", "local_whisper", "faster-whisper"):
        return LocalWhisperSTTProvider()
    elif name in ("mock", "test"):
        return MockSTTProvider()
    else:
        logger.warning("Unknown STT provider %r, falling back to groq", name)
        return GroqSTTProvider()
