"""
Unit and integration tests for the real-time streaming conversational voice pipeline.

Validates:
1. VoiceActivityDetector (WebRTC VAD, 20ms frame slicing, pre-padding, silence debounce)
2. ResponseChunker (progressive sentence & clause splitting, word threshold fallback)
3. ConversationManager (sliding-window history, voice prompt formatting, prune)
4. GroqClient (stream_chat_completion async generator & failover)
5. StreamingVoicePipeline (producer-consumer queues, fast path, streaming path, barge-in)
6. Voice WebSocket route /ws/voice (duplex text & binary protocol)
"""
from __future__ import annotations

import asyncio
import json
import os
import struct
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app.conversation.manager import ConversationManager, VOICE_SYSTEM_PROMPT
from app.services.groq_client import GroqClient
from app.voice.chunker import ResponseChunker
from app.voice.providers.mock_tts import MockTTSProvider
from app.voice.streaming_pipeline import (
    AudioQueueItem,
    PipelineLatencyMetrics,
    StreamingVoicePipeline,
)
from app.voice.vad import VoiceActivityDetector


# ══════════════════════════════════════════════════════════════════════════════
# 1. VoiceActivityDetector Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestVoiceActivityDetector:
    def test_initialization_defaults(self):
        vad = VoiceActivityDetector(sample_rate=16000, frame_duration_ms=20)
        assert vad.sample_rate == 16000
        assert vad.frame_size == 640  # 16000 * 20 / 1000 * 2 bytes
        assert vad.is_speaking is False

    def test_process_silence_chunk(self):
        vad = VoiceActivityDetector(sample_rate=16000, frame_duration_ms=20)
        silence_frame = b"\x00" * 640
        event, audio = vad.process_chunk(silence_frame)
        assert event is None
        assert audio is None
        assert vad.is_speaking is False

    def test_process_speech_and_silence_transition(self):
        vad = VoiceActivityDetector(
            sample_rate=16000,
            frame_duration_ms=20,
            silence_timeout_ms=40,  # 2 frames debounce
        )
        # High-amplitude square wave for VAD energy & WebRTC
        tone_samples = [int(18000 * (1 if (i % 20) < 10 else -1)) for i in range(320)]
        speech_frame = struct.pack(f"<{len(tone_samples)}h", *tone_samples)

        # Feed speech frame
        event, audio = vad.process_chunk(speech_frame)
        assert event == "speech_start"
        assert vad.is_speaking is True

        # Continue feeding speech
        event, audio = vad.process_chunk(speech_frame)
        assert event is None  # ongoing speech produces None event
        assert vad.is_speaking is True

        # Feed silence frames to trigger debounce and speech_final
        silence_frame = b"\x00" * 640
        event1, audio1 = vad.process_chunk(silence_frame)
        event2, audio2 = vad.process_chunk(silence_frame)
        event3, audio3 = vad.process_chunk(silence_frame)

        events = [event1, event2, event3]
        audios = [audio1, audio2, audio3]
        assert "speech_final" in events
        final_idx = events.index("speech_final")
        assert audios[final_idx] is not None
        assert len(audios[final_idx]) > 0
        assert vad.is_speaking is False

    def test_reset(self):
        vad = VoiceActivityDetector(sample_rate=16000, frame_duration_ms=20)
        vad._is_speaking = True
        vad.reset()
        assert vad.is_speaking is False
        assert len(vad._speech_frames) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 2. ResponseChunker Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestResponseChunker:
    def test_sentence_boundary_splitting(self):
        chunker = ResponseChunker(min_words_for_clause=4)
        tokens = ["Hello", " there! ", "How ", "are ", "you ", "doing? ", "I ", "am ", "ready."]

        emitted = []
        for t in tokens:
            chunks = chunker.add_token(t)
            emitted.extend(chunks)

        remainder = chunker.flush()
        if remainder:
            emitted.append(remainder)

        assert len(emitted) >= 2
        assert "Hello there!" in emitted[0]
        assert "How are you doing?" in emitted[1]

    def test_clause_splitting_on_word_threshold(self):
        chunker = ResponseChunker(min_words_for_clause=4)
        tokens = ["I ", "have ", "checked ", "the ", "weather, ", "and ", "it ", "is ", "sunny."]

        emitted = []
        for t in tokens:
            emitted.extend(chunker.add_token(t))
        rem = chunker.flush()
        if rem:
            emitted.append(rem)

        assert len(emitted) >= 2
        assert any("weather" in e for e in emitted)

    def test_word_count_fallback_on_long_sentence(self):
        chunker = ResponseChunker(min_words_for_clause=3, max_words_before_force_split=6)
        tokens = ["word "] * 10

        emitted = []
        for t in tokens:
            emitted.extend(chunker.add_token(t))
        rem = chunker.flush()
        if rem:
            emitted.append(rem)

        assert len(emitted) >= 2

    def test_reset_clears_buffer(self):
        chunker = ResponseChunker()
        chunker.add_token("Some unfinished sentence")
        chunker.reset()
        assert chunker.flush() is None


# ══════════════════════════════════════════════════════════════════════════════
# 3. ConversationManager Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConversationManager:
    def test_initial_messages_structure(self):
        mgr = ConversationManager(max_turns=3)
        messages = mgr.get_messages(current_prompt="Hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == VOICE_SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"

    def test_sliding_window_pruning(self):
        mgr = ConversationManager(max_turns=2)
        for i in range(5):
            mgr.add_user_message(f"User {i}")
            mgr.add_assistant_message(f"Assistant {i}")

        history = mgr.get_history()
        assert len(history) == 4
        assert history[0]["content"] == "User 3"
        assert history[-1]["content"] == "Assistant 4"

    def test_clear_history(self):
        mgr = ConversationManager()
        mgr.add_user_message("Test")
        mgr.clear()
        assert len(mgr.get_history()) == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. GroqClient Streaming Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGroqClientStreaming:
    @pytest.mark.asyncio
    async def test_stream_chat_completion_yields_deltas(self):
        client = GroqClient()

        class MockDelta:
            def __init__(self, content):
                self.content = content

        class MockChoice:
            def __init__(self, content):
                self.delta = MockDelta(content)

        class MockChunk:
            def __init__(self, content):
                self.choices = [MockChoice(content)]

        class MockStream:
            def __init__(self, items):
                self._items = list(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self._items:
                    raise StopAsyncIteration
                return self._items.pop(0)

        chunks = [MockChunk("Hello"), MockChunk(" world"), MockChunk("!")]
        mock_create = AsyncMock(return_value=MockStream(chunks))

        with patch.object(client._client.chat.completions, "create", mock_create):
            tokens = []
            async for token in client.stream_chat_completion([{"role": "user", "content": "hi"}]):
                tokens.append(token)

            assert tokens == ["Hello", " world", "!"]


# ══════════════════════════════════════════════════════════════════════════════
# 5. StreamingVoicePipeline Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestStreamingVoicePipeline:
    @pytest.mark.asyncio
    async def test_fast_router_bypass_execution(self):
        events = []

        async def callback(evt):
            events.append(evt)

        pipeline = StreamingVoicePipeline(event_callback=callback, enable_host_playback=False)
        pipeline.tts = MockTTSProvider()
        await pipeline.start()

        try:
            # Fast router matches greetings: "hello"
            await pipeline.process_text_prompt("hello")

            for _ in range(20):
                await asyncio.sleep(0.02)
                if any(e.get("type") == "assistant_done" for e in events):
                    break

            event_types = [e["type"] for e in events]
            assert "transcript_final" in event_types
            assert "llm_start" in event_types
            assert "llm_chunk" in event_types
            assert "assistant_done" in event_types

        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_barge_in_interruption(self):
        events = []

        async def callback(evt):
            events.append(evt)

        pipeline = StreamingVoicePipeline(event_callback=callback, enable_host_playback=False)
        pipeline.tts = MockTTSProvider()
        await pipeline.start()

        try:
            await pipeline.text_queue.put("Some sentence being processed")
            await pipeline.audio_queue.put(
                AudioQueueItem(chunk_index=0, text="Some sentence", audio_bytes=b"123")
            )
            pipeline.is_speaking = True

            # Trigger barge-in
            await pipeline.interrupt("user_speaking")

            assert pipeline.text_queue.empty()
            assert pipeline.audio_queue.empty()
            assert pipeline.is_speaking is False

            event_types = [e["type"] for e in events]
            assert "interrupted" in event_types

        finally:
            await pipeline.stop()

    @pytest.mark.asyncio
    async def test_streaming_llm_pipeline(self):
        events = []

        async def callback(evt):
            events.append(evt)

        pipeline = StreamingVoicePipeline(event_callback=callback, enable_host_playback=False)
        pipeline.tts = MockTTSProvider()

        # Mock Groq stream generator
        async def mock_stream_tokens(*args, **kwargs):
            yield "Artificial "
            yield "intelligence "
            yield "is fascinating. "

        pipeline.groq.stream_chat_completion = mock_stream_tokens  # type: ignore

        await pipeline.start()
        try:
            await pipeline.process_text_prompt("Tell me about AI")

            for _ in range(20):
                await asyncio.sleep(0.02)
                if any(e.get("type") == "assistant_done" for e in events):
                    break

            event_types = [e["type"] for e in events]
            assert "transcript_final" in event_types
            assert "llm_start" in event_types
            assert "llm_chunk" in event_types
            assert "tts_start" in event_types
            assert "audio_chunk" in event_types
            assert "assistant_done" in event_types

            done_event = next(e for e in events if e["type"] == "assistant_done")
            metrics = done_event.get("metrics", {})
            assert "time_to_first_audio_ms" in metrics
            assert metrics["time_to_first_audio_ms"] > 0

        finally:
            await pipeline.stop()


# ══════════════════════════════════════════════════════════════════════════════
# 6. /ws/voice WebSocket Endpoint Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestVoiceWebSocketRoute:
    def test_websocket_connect_and_ping(self):
        from app.main import app

        with TestClient(app) as client:
            with client.websocket_connect("/ws/voice") as websocket:
                greeting = websocket.receive_json()
                assert greeting["type"] == "connection_ready"

                websocket.send_json({"type": "ping"})
                pong = websocket.receive_json()
                assert pong["type"] == "pong"

    def test_websocket_interrupt_signal(self):
        from app.main import app

        with TestClient(app) as client:
            with client.websocket_connect("/ws/voice") as websocket:
                greeting = websocket.receive_json()
                assert greeting["type"] == "connection_ready"

                websocket.send_json({"type": "interrupt"})

                # Route now sends state_machine (INTERRUPTING) first, then
                # pipeline emits "interrupted", then route sends state_machine (IDLE).
                # Consume messages until we find "interrupted".
                found_interrupted = False
                for _ in range(5):  # safety: at most 5 messages
                    msg = websocket.receive_json()
                    if msg["type"] == "interrupted":
                        assert msg["reason"] == "client_request"
                        found_interrupted = True
                        break
                    # Accept state_machine transitions as expected side-effects
                    assert msg["type"] == "state_machine", f"Unexpected message: {msg}"
                assert found_interrupted, "Never received 'interrupted' event"
