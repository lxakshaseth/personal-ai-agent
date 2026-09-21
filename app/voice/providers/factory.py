"""
TTS Provider Factory.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.config.settings import get_settings
from app.voice.providers.base import TTSProvider
from app.voice.providers.mock_tts import MockTTSProvider
from app.voice.providers.openai_tts import OpenAITTSProvider
from app.voice.providers.system_tts import Pyttsx3TTSProvider, SystemTTSProvider

logger = logging.getLogger(__name__)

_tts_singleton: Optional[TTSProvider] = None


def get_tts_provider(provider_name: Optional[str] = None) -> TTSProvider:
    """
    Factory to obtain the configured TTSProvider.
    Uses cached instance when using the default configured provider.
    """
    global _tts_singleton
    settings = get_settings()
    name = (provider_name or settings.tts_provider).strip().lower()

    # If asking for default and we have a singleton, return it
    if provider_name is None and _tts_singleton is not None:
        if _tts_singleton.provider_name == name or (_tts_singleton.provider_name in ("system", "pyttsx3") and name in ("system", "pyttsx3", "windows", "default")):
            return _tts_singleton

    provider: TTSProvider
    if name in ("system", "windows", "default"):
        provider = SystemTTSProvider()
    elif name in ("pyttsx3", "sapi5"):
        provider = Pyttsx3TTSProvider()
    elif name in ("openai", "cloud"):
        provider = OpenAITTSProvider()
    elif name in ("mock", "test"):
        provider = MockTTSProvider()
    else:
        logger.warning("Unknown TTS provider %r, falling back to SystemTTSProvider", name)
        provider = SystemTTSProvider()

    if provider_name is None:
        _tts_singleton = provider

    return provider
