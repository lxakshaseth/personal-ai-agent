"""
Abstract Base Class for Text-to-Speech Providers.
"""
from __future__ import annotations

import abc
from typing import Optional


class TTSProvider(abc.ABC):
    """Abstract interface for text-to-speech engines."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Identifier for this provider (e.g., 'system', 'pyttsx3', 'openai', 'mock')."""
        ...

    @abc.abstractmethod
    async def speak(self, text: str) -> None:
        """Speak the given text aloud synchronously or via engine playback."""
        ...

    @abc.abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text into WAV/audio bytes."""
        ...

    def stop(self) -> None:
        """Interrupt and stop any currently active speech playback immediately."""
        pass
