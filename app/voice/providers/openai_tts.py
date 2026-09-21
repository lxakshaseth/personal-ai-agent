"""
OpenAI / Cloud TTS provider (optional cloud TTS).
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

from app.utils.exceptions import TextToSpeechError
from app.voice.providers.base import TTSProvider
from app.voice.providers.system_tts import SystemTTSProvider

logger = logging.getLogger(__name__)


class OpenAITTSProvider(TTSProvider):
    """
    TTS Provider using OpenAI Audio API with automatic fallback to System TTS.
    Never exposes API keys to client.
    """

    def __init__(self, model: str = "tts-1", voice: str = "alloy") -> None:
        self._model = model
        self._voice = voice
        self._fallback = SystemTTSProvider()
        self._api_key = os.getenv("OPENAI_API_KEY")

    @property
    def provider_name(self) -> str:
        return "openai"

    async def speak(self, text: str) -> None:
        if not self._api_key:
            logger.info("OPENAI_API_KEY not found; falling back to System TTS.")
            await self._fallback.speak(text)
            return

        try:
            audio_bytes = await self.synthesize(text)
            # Play synthesized audio via local player if available, else fallback
            if audio_bytes:
                await self._play_bytes(audio_bytes)
            else:
                await self._fallback.speak(text)
        except Exception as exc:
            logger.warning("OpenAI TTS failed (%s); falling back to System TTS", exc)
            await self._fallback.speak(text)

    async def synthesize(self, text: str) -> bytes:
        if not self._api_key:
            return await self._fallback.synthesize(text)

        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "voice": self._voice, "input": text},
                )
                if res.status_code == 200:
                    return res.content
                logger.warning("OpenAI TTS API error HTTP %d: %s", res.status_code, res.text)
        except Exception as exc:
            logger.warning("OpenAI TTS synthesize request failed: %s", exc)

        return await self._fallback.synthesize(text)

    async def _play_bytes(self, audio_bytes: bytes) -> None:
        """Play WAV/MP3 bytes using sounddevice or system player."""
        try:
            import numpy as np
            import sounddevice as sd
            import soundfile as sf

            data, samplerate = sf.read(io.BytesIO(audio_bytes))
            sd.play(data, samplerate)
            sd.wait()
        except Exception:
            # Fallback to system playback
            await self._fallback.speak("Audio output generated.")

    def stop(self) -> None:
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass
        self._fallback.stop()
