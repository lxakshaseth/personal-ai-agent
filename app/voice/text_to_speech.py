"""
Text-to-Speech provider abstraction and implementations.

Provides:
  - TextToSpeechProvider (ABC)
  - SystemTTSProvider (Windows SAPI5 with PowerShell fallback)
  - Pyttsx3TTSProvider (direct pyttsx3)
  - MockTTSProvider (deterministic mock for tests)
  - get_tts_provider() factory
"""
from __future__ import annotations

import abc
import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.config.settings import get_settings
from app.utils.exceptions import TextToSpeechError

logger = logging.getLogger(__name__)


class TextToSpeechProvider(abc.ABC):
    """Abstract interface for all text-to-speech providers."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of the TTS provider."""
        ...

    @abc.abstractmethod
    async def speak(self, text: str) -> None:
        """Speak the given text aloud."""
        ...

    @abc.abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text into WAV audio bytes."""
        ...


class Pyttsx3TTSProvider(TextToSpeechProvider):
    """Text-to-speech provider using pyttsx3 (SAPI5 on Windows)."""

    def __init__(
        self,
        rate: int = 180,
        volume: float = 1.0,
        voice_index: int = 0,
    ) -> None:
        self._rate = rate
        self._volume = volume
        self._voice_index = voice_index
        self._engine = None

    @property
    def provider_name(self) -> str:
        return "pyttsx3"

    def _get_engine(self):
        if self._engine is None:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self._rate)
                engine.setProperty("volume", self._volume)
                voices = engine.getProperty("voices")
                if voices and self._voice_index < len(voices):
                    engine.setProperty("voice", voices[self._voice_index].id)
                self._engine = engine
            except ImportError as exc:
                raise TextToSpeechError(
                    "pyttsx3 is not installed. Install with: pip install pyttsx3"
                ) from exc
            except Exception as exc:
                raise TextToSpeechError(f"Failed to initialise pyttsx3 engine: {exc}") from exc
        return self._engine

    async def speak(self, text: str) -> None:
        if not text.strip():
            return
        loop = asyncio.get_running_loop()

        def _speak_sync():
            engine = self._get_engine()
            engine.say(text)
            engine.runAndWait()

        try:
            await loop.run_in_executor(None, _speak_sync)
        except Exception as exc:
            raise TextToSpeechError(f"pyttsx3 speak failed: {exc}") from exc

    async def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        loop = asyncio.get_running_loop()

        def _synthesize_sync() -> bytes:
            engine = self._get_engine()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                return Path(tmp_path).read_bytes()
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        try:
            return await loop.run_in_executor(None, _synthesize_sync)
        except Exception as exc:
            raise TextToSpeechError(f"pyttsx3 synthesize failed: {exc}") from exc


class SystemTTSProvider(TextToSpeechProvider):
    """
    Windows native system TTS provider.
    Tries pyttsx3 first; if not installed, uses Windows System.Speech via PowerShell.
    Zero mandatory third-party dependencies on Windows.
    """

    def __init__(self) -> None:
        self._pyttsx3_provider = None

    @property
    def provider_name(self) -> str:
        return "system"

    def _try_pyttsx3(self) -> Optional[Pyttsx3TTSProvider]:
        if self._pyttsx3_provider is None:
            try:
                import pyttsx3  # noqa: F401
                self._pyttsx3_provider = Pyttsx3TTSProvider()
            except ImportError:
                self._pyttsx3_provider = False  # Mark unavailable
        return self._pyttsx3_provider if self._pyttsx3_provider is not False else None

    async def speak(self, text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return

        pyttsx3_prov = self._try_pyttsx3()
        if pyttsx3_prov:
            try:
                await pyttsx3_prov.speak(clean_text)
                return
            except Exception as e:
                logger.debug("pyttsx3 failed, falling back to PowerShell SAPI: %s", e)

        # PowerShell SAPI5 fallback
        escaped = clean_text.replace("'", "''").replace('"', '`"')
        ps_cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Speak('{escaped}')"
        )
        loop = asyncio.get_running_loop()

        def _ps_speak():
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True,
                timeout=30,
            )

        try:
            await loop.run_in_executor(None, _ps_speak)
        except Exception as exc:
            logger.warning("PowerShell TTS failed: %s", exc)
            raise TextToSpeechError(f"System TTS failed: {exc}") from exc

    async def synthesize(self, text: str) -> bytes:
        pyttsx3_prov = self._try_pyttsx3()
        if pyttsx3_prov:
            return await pyttsx3_prov.synthesize(text)
        return b""


class MockTTSProvider(TextToSpeechProvider):
    """Mock TTS provider that records spoken phrases without playing sound."""

    def __init__(self) -> None:
        self.spoken_phrases: list[str] = []

    @property
    def provider_name(self) -> str:
        return "mock"

    async def speak(self, text: str) -> None:
        logger.debug("MockTTSProvider speaking: %s", text)
        self.spoken_phrases.append(text)

    async def synthesize(self, text: str) -> bytes:
        self.spoken_phrases.append(text)
        return b"RIFFMOCKWAVEDATA"


def get_tts_provider(provider_name: Optional[str] = None) -> TextToSpeechProvider:
    """Factory to obtain the configured TextToSpeechProvider."""
    name = (provider_name or get_settings().tts_provider).strip().lower()

    if name in ("system", "windows", "default"):
        return SystemTTSProvider()
    elif name in ("pyttsx3", "sapi5"):
        return Pyttsx3TTSProvider()
    elif name in ("mock", "test"):
        return MockTTSProvider()
    else:
        logger.warning("Unknown TTS provider %r, falling back to SystemTTSProvider", name)
        return SystemTTSProvider()
