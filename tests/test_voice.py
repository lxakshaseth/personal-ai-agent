"""
Unit tests for the voice interface.

Verifies:
- SpeechToTextProvider implementations and factory (Groq, OpenAI, Whisper, Mock)
- TextToSpeechProvider implementations and factory (System, Pyttsx3, Mock)
- MicrophoneRecorder (availability check, silence detection, device errors)
- Wake word detection and command cleaning (e.g. 'Jarvis, open YouTube' -> 'open YouTube')
- End-to-end voice loop (Microphone -> STT -> Agent -> Tool execution -> TTS)
- Error handling (mic unavailable, no speech detected, STT failure, API failure, timeout)
- Fallback to keyboard text commands when voice is disabled
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.agent.agent import PersonalAgent
from app.agent.base import AgentInput, AgentOutput
from app.config.settings import Settings
from app.utils.exceptions import (
    MicrophoneUnavailableError,
    NoSpeechDetectedError,
    SpeechRecognitionError,
    TextToSpeechError,
    VoiceTimeoutError,
)
from app.voice.microphone import (
    MicrophoneRecorder,
    MockMicrophoneRecorder,
    is_microphone_available,
)
from app.voice.schemas import AudioData, AudioFormat, VoiceMode
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
from app.voice.voice_controller import VoiceController


# ══════════════════════════════════════════════════════════════════════════════
# SPEECH-TO-TEXT PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestSpeechToTextProviders:
    @pytest.mark.asyncio
    async def test_mock_stt_returns_fixed_text(self) -> None:
        stt = MockSTTProvider(fixed_text="open YouTube")
        result = await stt.transcribe(b"fake_audio")
        assert result.text == "open YouTube"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_mock_stt_queued_transcripts(self) -> None:
        stt = MockSTTProvider()
        stt.queue_transcript("first phrase")
        stt.queue_transcript("second phrase")
        r1 = await stt.transcribe(b"audio1")
        r2 = await stt.transcribe(b"audio2")
        assert r1.text == "first phrase"
        assert r2.text == "second phrase"

    @pytest.mark.asyncio
    async def test_groq_stt_transcription(self) -> None:
        """GroqSTTProvider correctly invokes the Groq audio transcriptions API."""
        mock_groq = MagicMock()
        mock_transcription = MagicMock()
        mock_transcription.text = "create a folder called test"
        mock_groq.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)

        stt = GroqSTTProvider(api_key="test_key")
        stt._client = mock_groq

        audio = AudioData(audio_bytes=b"RIFFWAVEDATA", duration_seconds=2.0)
        result = await stt.transcribe(audio)

        assert result.text == "create a folder called test"
        mock_groq.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_groq.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-large-v3-turbo"

    @pytest.mark.asyncio
    async def test_groq_stt_error_handling(self) -> None:
        mock_groq = MagicMock()
        mock_groq.audio.transcriptions.create = AsyncMock(side_effect=Exception("API Connection Failed"))

        stt = GroqSTTProvider(api_key="test_key")
        stt._client = mock_groq

        with pytest.raises(SpeechRecognitionError) as exc_info:
            await stt.transcribe(b"audio")
        assert "API Connection Failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_openai_stt_without_key_raises(self) -> None:
        stt = OpenAISTTProvider(api_key="")
        with pytest.raises(SpeechRecognitionError):
            await stt.transcribe(b"audio")

    def test_get_stt_provider_factory(self) -> None:
        assert isinstance(get_stt_provider("mock"), MockSTTProvider)
        assert isinstance(get_stt_provider("groq"), GroqSTTProvider)
        assert isinstance(get_stt_provider("whisper"), LocalWhisperSTTProvider)
        assert isinstance(get_stt_provider("openai"), OpenAISTTProvider)


# ══════════════════════════════════════════════════════════════════════════════
# TEXT-TO-SPEECH PROVIDERS
# ══════════════════════════════════════════════════════════════════════════════

class TestTextToSpeechProviders:
    @pytest.mark.asyncio
    async def test_mock_tts_records_spoken_phrases(self) -> None:
        tts = MockTTSProvider()
        await tts.speak("Hello Akshat")
        await tts.speak("Opening YouTube")
        assert len(tts.spoken_phrases) == 2
        assert tts.spoken_phrases[0] == "Hello Akshat"
        assert tts.spoken_phrases[1] == "Opening YouTube"

    @pytest.mark.asyncio
    async def test_system_tts_calls_pyttsx3_or_powershell(self) -> None:
        """SystemTTSProvider executes speech without raising errors."""
        tts = SystemTTSProvider()
        # Patch both pyttsx3 and subprocess to verify fallback behavior
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch.object(tts, "_try_pyttsx3", return_value=None):
                await tts.speak("System speech test")
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert "powershell" in args[0]
                assert "System.Speech" in args[4]

    def test_get_tts_provider_factory(self) -> None:
        assert isinstance(get_tts_provider("mock"), MockTTSProvider)
        assert isinstance(get_tts_provider("system"), SystemTTSProvider)
        assert isinstance(get_tts_provider("pyttsx3"), Pyttsx3TTSProvider)


# ══════════════════════════════════════════════════════════════════════════════
# MICROPHONE RECORDER
# ══════════════════════════════════════════════════════════════════════════════

class TestMicrophoneRecorder:
    @pytest.mark.asyncio
    async def test_mock_microphone_records_audio(self) -> None:
        audio_in = AudioData(audio_bytes=b"MOCKWAV", duration_seconds=1.5)
        recorder = MockMicrophoneRecorder(audio_data=audio_in)
        audio_out = await recorder.record_phrase()
        assert audio_out.audio_bytes == b"MOCKWAV"
        assert audio_out.duration_seconds == 1.5

    @pytest.mark.asyncio
    async def test_mock_microphone_unavailable(self) -> None:
        recorder = MockMicrophoneRecorder()
        recorder.set_available(False)
        assert not recorder.is_available()
        with pytest.raises(MicrophoneUnavailableError):
            await recorder.record_phrase()

    @pytest.mark.asyncio
    async def test_mock_microphone_silence_raises_no_speech(self) -> None:
        recorder = MockMicrophoneRecorder(
            exception_to_raise=NoSpeechDetectedError("Silence")
        )
        with pytest.raises(NoSpeechDetectedError):
            await recorder.record_phrase()

    @pytest.mark.asyncio
    async def test_mock_microphone_timeout_raises_voice_timeout(self) -> None:
        recorder = MockMicrophoneRecorder(
            exception_to_raise=VoiceTimeoutError("Timed out")
        )
        with pytest.raises(VoiceTimeoutError):
            await recorder.record_phrase()


# ══════════════════════════════════════════════════════════════════════════════
# WAKE WORD PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

class TestWakeWord:
    def test_wake_word_disabled_accepts_all(self) -> None:
        settings = Settings(
            groq_api_key="test_key",
            wake_word_enabled=False,
            wake_word="Jarvis",
        )
        controller = VoiceController(
            agent=MagicMock(),
            recorder=MockMicrophoneRecorder(),
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
            settings=settings,
        )
        res = controller.check_wake_word("Open YouTube")
        assert res.detected is True
        assert res.command_text == "Open YouTube"

    def test_wake_word_enabled_matching(self) -> None:
        settings = Settings(
            groq_api_key="test_key",
            wake_word_enabled=True,
            wake_word="Jarvis",
        )
        controller = VoiceController(
            agent=MagicMock(),
            recorder=MockMicrophoneRecorder(),
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
            settings=settings,
        )
        # Standard "Jarvis, open YouTube"
        res1 = controller.check_wake_word("Jarvis, open YouTube")
        assert res1.detected is True
        assert res1.command_text == "open YouTube"

        # Without comma: "Jarvis open VS Code"
        res2 = controller.check_wake_word("Jarvis open VS Code")
        assert res2.detected is True
        assert res2.command_text == "open VS Code"

        # Embedded: "hey Jarvis create a folder"
        res3 = controller.check_wake_word("hey Jarvis create a folder")
        assert res3.detected is True
        assert res3.command_text == "create a folder"

    def test_wake_word_enabled_not_matching(self) -> None:
        settings = Settings(
            groq_api_key="test_key",
            wake_word_enabled=True,
            wake_word="Jarvis",
        )
        controller = VoiceController(
            agent=MagicMock(),
            recorder=MockMicrophoneRecorder(),
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
            settings=settings,
        )
        res = controller.check_wake_word("Open YouTube")
        assert res.detected is False
        assert res.command_text == ""


# ══════════════════════════════════════════════════════════════════════════════
# END-TO-END VOICE CONTROLLER FLOW
# ══════════════════════════════════════════════════════════════════════════════

class TestVoiceControllerEndToEnd:
    @pytest.fixture
    def mock_agent(self) -> MagicMock:
        agent = MagicMock(spec=PersonalAgent)
        output = AgentOutput(
            success=True,
            response="Opening YouTube.",
            tool_calls=[{"tool": "open_url", "args": {"url": "https://www.youtube.com"}, "success": True, "output": "Opened: https://www.youtube.com", "error": None}],
        )
        agent.run = AsyncMock(return_value=output)
        return agent

    @pytest.fixture
    def mock_stt(self) -> MockSTTProvider:
        return MockSTTProvider(fixed_text="Open YouTube")

    @pytest.fixture
    def mock_tts(self) -> MockTTSProvider:
        return MockTTSProvider()

    @pytest.fixture
    def mock_recorder(self) -> MockMicrophoneRecorder:
        return MockMicrophoneRecorder(
            audio_data=AudioData(audio_bytes=b"RIFFWAVE", duration_seconds=1.0)
        )

    @pytest.mark.asyncio
    async def test_full_voice_turn(
        self,
        mock_agent: MagicMock,
        mock_recorder: MockMicrophoneRecorder,
        mock_stt: MockSTTProvider,
        mock_tts: MockTTSProvider,
    ) -> None:
        """
        Microphone -> STT ('Open YouTube') -> Agent (tool=open_url) -> TTS ('Opening YouTube.')
        """
        settings = Settings(
            groq_api_key="test_key",
            wake_word_enabled=False,
            voice_enabled=True,
        )
        controller = VoiceController(
            agent=mock_agent,
            recorder=mock_recorder,
            stt_provider=mock_stt,
            tts_provider=mock_tts,
            settings=settings,
        )

        audio = await mock_recorder.record_phrase()
        result = await controller.process_audio(audio)

        assert result.success is True
        assert result.command_text == "Open YouTube"
        assert result.spoken_response == "Opening YouTube."
        assert len(mock_tts.spoken_phrases) == 1
        assert mock_tts.spoken_phrases[0] == "Opening YouTube."
        mock_agent.run.assert_called_once()
        assert mock_agent.run.call_args[0][0].command == "Open YouTube"

    @pytest.mark.asyncio
    async def test_wake_word_voice_turn(
        self,
        mock_agent: MagicMock,
        mock_recorder: MockMicrophoneRecorder,
        mock_tts: MockTTSProvider,
    ) -> None:
        """With wake word enabled, 'Jarvis, open YouTube' triggers agent with 'open YouTube'."""
        stt = MockSTTProvider(fixed_text="Jarvis, open YouTube")
        settings = Settings(
            groq_api_key="test_key",
            wake_word_enabled=True,
            wake_word="Jarvis",
            voice_enabled=True,
        )
        controller = VoiceController(
            agent=mock_agent,
            recorder=mock_recorder,
            stt_provider=stt,
            tts_provider=mock_tts,
            settings=settings,
        )

        audio = await mock_recorder.record_phrase()
        result = await controller.process_audio(audio)

        assert result.success is True
        assert result.wake_word_detected is True
        assert result.command_text == "open YouTube"
        assert mock_agent.run.call_args[0][0].command == "open YouTube"

    @pytest.mark.asyncio
    async def test_text_command_mode_when_voice_disabled(
        self,
        mock_agent: MagicMock,
        mock_tts: MockTTSProvider,
    ) -> None:
        """Text-command execution works directly through execute_command."""
        settings = Settings(
            groq_api_key="test_key",
            voice_enabled=False,
        )
        controller = VoiceController(
            agent=mock_agent,
            recorder=MockMicrophoneRecorder(),
            stt_provider=MockSTTProvider(),
            tts_provider=mock_tts,
            settings=settings,
        )

        result = await controller.execute_command("Create a folder called AI Projects")

        assert result.success is True
        assert result.command_text == "Create a folder called AI Projects"
        mock_agent.run.assert_called_once()
        assert mock_agent.run.call_args[0][0].command == "Create a folder called AI Projects"

    @pytest.mark.asyncio
    async def test_stt_failure_handled_gracefully(
        self,
        mock_agent: MagicMock,
        mock_recorder: MockMicrophoneRecorder,
        mock_tts: MockTTSProvider,
    ) -> None:
        """STT failure reports an error without crashing."""
        stt = MockSTTProvider()
        stt.transcribe = AsyncMock(side_effect=SpeechRecognitionError("Network error connecting to Whisper API"))

        controller = VoiceController(
            agent=mock_agent,
            recorder=mock_recorder,
            stt_provider=stt,
            tts_provider=mock_tts,
        )

        audio = await mock_recorder.record_phrase()
        result = await controller.process_audio(audio)

        assert result.success is False
        assert "Speech recognition failed" in result.error
        mock_agent.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_failure_speaks_error_response(
        self,
        mock_recorder: MockMicrophoneRecorder,
        mock_tts: MockTTSProvider,
    ) -> None:
        """When agent encounters an unexpected exception, error is spoken and recorded."""
        agent = MagicMock(spec=PersonalAgent)
        agent.run = AsyncMock(side_effect=Exception("Groq API quota exhausted"))

        controller = VoiceController(
            agent=agent,
            recorder=mock_recorder,
            stt_provider=MockSTTProvider(fixed_text="run backend"),
            tts_provider=mock_tts,
        )

        audio = await mock_recorder.record_phrase()
        result = await controller.process_audio(audio)

        assert result.success is False
        assert "Agent failed" in result.error
        assert len(mock_tts.spoken_phrases) == 1
        assert "error" in mock_tts.spoken_phrases[0].lower()
