"""
Deterministic Mock TTS Provider for testing.
"""
from __future__ import annotations

import logging
from app.voice.providers.base import TTSProvider

logger = logging.getLogger(__name__)


class MockTTSProvider(TTSProvider):
    """Mock TTS provider that records spoken phrases without playing audio."""

    def __init__(self) -> None:
        self.spoken_phrases: list[str] = []
        self._stopped = False

    @property
    def provider_name(self) -> str:
        return "mock"

    async def speak(self, text: str) -> None:
        self._stopped = False
        logger.debug("MockTTSProvider speaking: %s", text)
        self.spoken_phrases.append(text)

    async def synthesize(self, text: str) -> bytes:
        self.spoken_phrases.append(text)
        return b"RIFFMOCKWAVEDATA"

    def stop(self) -> None:
        self._stopped = True
