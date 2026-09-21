"""
System and Pyttsx3 TTS Provider for Windows native speech.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from app.utils.exceptions import TextToSpeechError
from app.voice.providers.base import TTSProvider

logger = logging.getLogger(__name__)


def _silence_noisy_comtypes() -> None:
    for name in ("comtypes", "comtypes.client", "comtypes._comobject", "comtypes._vtbl"):
        logging.getLogger(name).setLevel(logging.WARNING)


class WindowsSapiTTSProvider(TTSProvider):
    """
    Direct Windows SAPI5 TTS provider using pywin32 (win32com).
    Bypasses comtypes and pyttsx3 event hooks for ultra-fast, zero-overhead speech.
    """

    def __init__(self, rate: int = 1, volume: int = 100) -> None:
        self._rate = rate
        self._volume = volume
        self._is_stopped = False

    @property
    def provider_name(self) -> str:
        return "windows_sapi"

    async def speak(self, text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return

        self._is_stopped = False
        loop = asyncio.get_running_loop()

        def _speak_sync() -> None:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Rate = self._rate
                voice.Volume = self._volume
                voice.Speak(clean_text, 0)
            except Exception as e:
                logger.warning("Windows SAPI SpVoice speak error: %s", e)
                raise
            finally:
                pythoncom.CoUninitialize()

        try:
            await loop.run_in_executor(None, _speak_sync)
        except Exception as exc:
            raise TextToSpeechError(f"Windows SAPI speak failed: {exc}") from exc

    def stop(self) -> None:
        self._is_stopped = True
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                # Flag 2 = SVSFPurgeBeforeSpeak, immediately purges speech queue
                voice.Speak("", 2)
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug("Error stopping Windows SAPI SpVoice: %s", e)

    async def synthesize(self, text: str) -> bytes:
        return b""


class Pyttsx3TTSProvider(TTSProvider):
    """Text-to-speech provider using pyttsx3 (SAPI5 on Windows)."""

    def __init__(
        self,
        rate: int = 190,
        volume: float = 1.0,
        voice_index: int = 0,
    ) -> None:
        _silence_noisy_comtypes()
        self._rate = rate
        self._volume = volume
        self._voice_index = voice_index
        self._engine = None
        self._lock = threading.Lock()
        self._is_stopped = False

    @property
    def provider_name(self) -> str:
        return "pyttsx3"

    def _get_engine(self):
        _silence_noisy_comtypes()
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
        clean_text = text.strip()
        if not clean_text:
            return

        self._is_stopped = False
        loop = asyncio.get_running_loop()

        def _speak_sync():
            with self._lock:
                if self._is_stopped:
                    return

                # 1. Ultra-fast direct SAPI (pywin32, <15ms, zero comtypes logging)
                try:
                    import pythoncom
                    import win32com.client

                    pythoncom.CoInitialize()
                    try:
                        voice = win32com.client.Dispatch("SAPI.SpVoice")
                        voice.Rate = 1
                        voice.Volume = int(self._volume * 100)
                        voice.Speak(clean_text, 0)
                        return
                    finally:
                        pythoncom.CoUninitialize()
                except Exception as e:
                    logger.debug("Direct win32com SAPI speak failed/skipped: %s", e)

                # 2. Pyttsx3 fallback with silenced comtypes
                engine = self._get_engine()
                try:
                    engine.say(clean_text)
                    engine.runAndWait()
                except Exception as exc:
                    logger.warning("pyttsx3 engine speech error: %s", exc)

        try:
            await loop.run_in_executor(None, _speak_sync)
        except Exception as exc:
            raise TextToSpeechError(f"pyttsx3 speak failed: {exc}") from exc

    def stop(self) -> None:
        """Attempt to stop ongoing playback."""
        self._is_stopped = True
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            try:
                voice = win32com.client.Dispatch("SAPI.SpVoice")
                voice.Speak("", 2)
            finally:
                pythoncom.CoUninitialize()
        except Exception:
            pass

        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception as exc:
            logger.debug("Error while stopping pyttsx3 engine: %s", exc)

    async def synthesize(self, text: str) -> bytes:
        clean_text = text.strip()
        if not clean_text:
            return b""

        loop = asyncio.get_running_loop()

        def _synthesize_sync() -> bytes:
            with self._lock:
                engine = self._get_engine()
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    engine.save_to_file(clean_text, tmp_path)
                    engine.runAndWait()
                    return Path(tmp_path).read_bytes()
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

        try:
            return await loop.run_in_executor(None, _synthesize_sync)
        except Exception as exc:
            raise TextToSpeechError(f"pyttsx3 synthesize failed: {exc}") from exc


class SystemTTSProvider(TTSProvider):
    """
    Windows native system TTS provider.
    Prefers pyttsx3 (with ultra-fast direct SAPI under the hood);
    falls back to Windows System.Speech via PowerShell.
    """

    def __init__(self) -> None:
        self._pyttsx3_provider: Optional[Pyttsx3TTSProvider] = None
        self._checked_pyttsx3 = False
        self._current_process: Optional[subprocess.Popen] = None

    @property
    def provider_name(self) -> str:
        return "system"

    def _try_pyttsx3(self) -> Optional[Pyttsx3TTSProvider]:
        if not self._checked_pyttsx3:
            try:
                import pyttsx3  # noqa: F401

                self._pyttsx3_provider = Pyttsx3TTSProvider()
            except Exception:
                self._pyttsx3_provider = None
            self._checked_pyttsx3 = True
        return self._pyttsx3_provider

    _get_pyttsx3 = _try_pyttsx3

    async def speak(self, text: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return

        py_prov = self._try_pyttsx3()
        if py_prov:
            try:
                await py_prov.speak(clean_text)
                return
            except Exception as e:
                logger.debug("pyttsx3 speak failed, attempting PowerShell SAPI: %s", e)

        # Fallback: PowerShell SAPI5
        escaped = clean_text.replace("'", "''").replace('"', '`"')
        ps_cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$synth.Speak('{escaped}')"
        )
        loop = asyncio.get_running_loop()

        def _ps_speak():
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    timeout=30,
                )
            except Exception as exc:
                logger.warning("PowerShell TTS playback error: %s", exc)

        try:
            await loop.run_in_executor(None, _ps_speak)
        except Exception as exc:
            raise TextToSpeechError(f"System TTS failed: {exc}") from exc

    def stop(self) -> None:
        py_prov = self._get_pyttsx3()
        if py_prov:
            py_prov.stop()
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
            self._current_process = None

    async def synthesize(self, text: str) -> bytes:
        py_prov = self._get_pyttsx3()
        if py_prov:
            return await py_prov.synthesize(text)
        return b""
