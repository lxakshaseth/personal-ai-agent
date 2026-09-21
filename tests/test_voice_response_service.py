"""
Tests for VoiceResponseService and TTS providers.
"""
import asyncio
import pytest

from app.services.event_bus import AgentStatus, get_event_bus
from app.voice.providers.factory import get_tts_provider
from app.voice.providers.mock_tts import MockTTSProvider
from app.voice.voice_response_service import VoiceResponseService


@pytest.fixture
def mock_service():
    service = VoiceResponseService()
    service._provider = MockTTSProvider()
    return service


@pytest.mark.asyncio
async def test_voice_response_service_speak(mock_service):
    await mock_service.speak("Test speech output")
    assert "Test speech output" in mock_service._provider.spoken_phrases
    assert mock_service.is_speaking is False


@pytest.mark.asyncio
async def test_voice_response_service_speak_async(mock_service):
    task = mock_service.speak_async("Asynchronous speech")
    assert isinstance(task, asyncio.Task)
    await task
    assert "Asynchronous speech" in mock_service._provider.spoken_phrases
    assert mock_service.is_speaking is False


@pytest.mark.asyncio
async def test_voice_response_service_stop(mock_service):
    # Call stop
    mock_service.stop()
    assert mock_service.is_speaking is False
    assert get_event_bus().current_status == AgentStatus.ONLINE
