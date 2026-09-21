"""
Dedicated VoiceResponseService for non-blocking speech playback and audio lifecycle.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.config.settings import get_settings
from app.services.event_bus import AgentStatus, get_event_bus
from app.voice.providers.factory import get_tts_provider

logger = logging.getLogger(__name__)


class VoiceResponseService:
    """
    Manages speech output lifecycle independently from UI rendering.

    Guarantees:
    - Never blocks HTTP response generation or UI rendering.
    - Transitions agent state: SPEAKING -> IDLE (or READY).
    - Exposes stop() for immediate interruption (e.g. Esc or user saying 'Stop').
    - Provides is_speaking flag to pause or prevent microphone recording during output.
    - Resilient: TTS failure never breaks the agent or UI.
    """

    def __init__(self) -> None:
        self._provider = get_tts_provider()
        self._current_task: Optional[asyncio.Task] = None
        self._is_speaking = False
        self._lock = asyncio.Lock()

    @property
    def is_speaking(self) -> bool:
        """True when NOVA is actively synthesizing or playing audio aloud."""
        return self._is_speaking

    def stop(self) -> None:
        """Immediately interrupt and stop any ongoing speech playback."""
        logger.info("VoiceResponseService: stopping active speech playback.")
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._current_task = None

        self._is_speaking = False
        try:
            self._provider.stop()
        except Exception as e:
            logger.debug("Error stopping TTS provider: %s", e)

        bus = get_event_bus()
        bus.set_status(AgentStatus.ONLINE, "Ready")
        bus.publish_event("agent.state", {"state": "IDLE", "detail": "Ready"})

    def speak_async(self, text: str, request_id: Optional[str] = None) -> asyncio.Task:
        """
        Schedule speech playback in a background task without blocking the caller.
        Returns the asyncio Task handle.
        """
        # Stop any prior speech in progress
        self.stop()

        clean_text = text.strip()
        if not clean_text:
            loop = asyncio.get_event_loop()
            return loop.create_task(asyncio.sleep(0))

        task = asyncio.create_task(self._run_speech(clean_text, request_id))
        self._current_task = task
        return task

    async def speak(self, text: str, request_id: Optional[str] = None) -> None:
        """
        Synchronously (awaitable) speak the text.
        Useful when the caller explicitly wants to wait for completion.
        """
        clean_text = text.strip()
        if not clean_text:
            return
        await self._run_speech(clean_text, request_id)

    async def _run_speech(self, text: str, request_id: Optional[str] = None) -> None:
        bus = get_event_bus()
        settings = get_settings()

        if not settings.voice_enabled:
            logger.debug("Voice output disabled in settings; skipping TTS.")
            return

        self._is_speaking = True
        start_t = time.time()

        # Emit state: SPEAKING
        bus.set_status(AgentStatus.SPEAKING, "Speaking response...")
        bus.publish_event(
            "agent.state",
            {
                "state": "SPEAKING",
                "request_id": request_id,
                "text": text[:80] + "..." if len(text) > 80 else text,
            },
        )

        try:
            provider = self._provider or get_tts_provider()
            await provider.speak(text)
            tts_ms = round((time.time() - start_t) * 1000, 1)
            if getattr(settings, "debug_performance", False):
                logger.info("[TTS] Playback completed in %0.1fms", tts_ms)
        except asyncio.CancelledError:
            logger.info("VoiceResponseService speech task cancelled.")
            try:
                self._provider.stop()
            except Exception:
                pass
            raise
        except Exception as exc:
            logger.warning("TTS speech failed: %s. Text response remains valid.", exc)
            bus.publish_event("agent.warning", {"message": "Voice playback unavailable", "error": str(exc)})
        finally:
            self._is_speaking = False
            # Return agent state back to ONLINE/IDLE
            if bus.current_status == AgentStatus.SPEAKING:
                bus.set_status(AgentStatus.ONLINE, "Ready")
                bus.publish_event("agent.state", {"state": "IDLE", "detail": "Ready", "request_id": request_id})


# Global Singleton
_voice_service: Optional[VoiceResponseService] = None


def get_voice_service() -> VoiceResponseService:
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceResponseService()
    return _voice_service
