"""
Real-Time Streaming Conversational Voice Pipeline.
Implements the fully concurrent, overlapping audio architecture:
Audio Capture -> VAD -> STT -> Streaming LLM -> Chunker -> TTS Queue -> Playback
with Barge-in interruption and precise microsecond latency instrumentation.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from app.agent.fast_router import FastRouter, ResponseMode
from app.conversation.manager import get_conversation_manager
from app.services.event_bus import AgentStatus, get_event_bus
from app.services.groq_client import get_groq_client
from app.voice.chunker import ResponseChunker
from app.voice.providers.factory import get_tts_provider
from app.voice.speech_to_text import get_stt_provider
from app.voice.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)


@dataclass
class PipelineLatencyMetrics:
    """Latency milestones for tracking Time-To-First-Audio (TTFA)."""
    user_speech_final_ts: float = 0.0
    stt_completed_ts: float = 0.0
    llm_request_ts: float = 0.0
    llm_first_token_ts: float = 0.0
    chunker_first_sentence_ts: float = 0.0
    tts_first_audio_ts: float = 0.0
    playback_start_ts: float = 0.0

    @property
    def stt_latency_ms(self) -> float:
        if self.user_speech_final_ts and self.stt_completed_ts:
            return round((self.stt_completed_ts - self.user_speech_final_ts) * 1000, 1)
        return 0.0

    @property
    def llm_first_token_ms(self) -> float:
        if self.llm_request_ts and self.llm_first_token_ts:
            return round((self.llm_first_token_ts - self.llm_request_ts) * 1000, 1)
        return 0.0

    @property
    def tts_first_audio_ms(self) -> float:
        if self.chunker_first_sentence_ts and self.tts_first_audio_ts:
            return round((self.tts_first_audio_ts - self.chunker_first_sentence_ts) * 1000, 1)
        return 0.0

    @property
    def time_to_first_audio_ms(self) -> float:
        """Total elapsed time from user finishing speech to first sound played."""
        start = self.user_speech_final_ts or self.llm_request_ts
        finish = self.playback_start_ts or self.tts_first_audio_ts
        if start and finish and finish >= start:
            return round((finish - start) * 1000, 1)
        return 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "stt_latency_ms": self.stt_latency_ms,
            "llm_first_token_ms": self.llm_first_token_ms,
            "tts_first_audio_ms": self.tts_first_audio_ms,
            "time_to_first_audio_ms": self.time_to_first_audio_ms,
        }


@dataclass
class AudioQueueItem:
    chunk_index: int
    text: str
    audio_bytes: bytes
    is_final: bool = False


class StreamingVoicePipeline:
    """
    Coordinates asynchronous streaming pipeline stages:
    1. VAD Speech Segmentation
    2. Fast Whisper Transcription
    3. Fast Router or Streaming Groq LLM
    4. Adaptive Sentence Chunking
    5. Concurrent TTS Worker & Playback Worker
    6. Barge-in / Interruption
    """

    def __init__(
        self,
        event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
        enable_host_playback: bool = True,
    ) -> None:
        self.event_callback = event_callback
        self.enable_host_playback = enable_host_playback

        self.vad = VoiceActivityDetector()
        self.stt = get_stt_provider()
        self.tts = get_tts_provider()
        self.chunker = ResponseChunker()
        self.conv_mgr = get_conversation_manager()
        self.groq = get_groq_client()

        # Producer-Consumer Queues
        self.text_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self.audio_queue: asyncio.Queue[Optional[AudioQueueItem]] = asyncio.Queue()

        # Lifecycle & Tasks
        self.is_active = False
        self.is_speaking = False
        self._current_gen_task: Optional[asyncio.Task] = None
        self._tts_worker_task: Optional[asyncio.Task] = None
        self._playback_worker_task: Optional[asyncio.Task] = None
        self.metrics = PipelineLatencyMetrics()

    async def start(self) -> None:
        """Start the background TTS and Playback worker loops."""
        if self.is_active:
            return
        self.is_active = True
        self._tts_worker_task = asyncio.create_task(self._tts_worker())
        self._playback_worker_task = asyncio.create_task(self._playback_worker())
        logger.debug("StreamingVoicePipeline workers started.")

    async def stop(self) -> None:
        """Stop all background worker tasks."""
        self.is_active = False
        await self.interrupt("pipeline_shutdown")
        if self._tts_worker_task and not self._tts_worker_task.done():
            self._tts_worker_task.cancel()
        if self._playback_worker_task and not self._playback_worker_task.done():
            self._playback_worker_task.cancel()

    async def interrupt(self, reason: str = "barge_in") -> None:
        """
        Immediately interrupt ongoing generation, purge audio queues,
        and stop audio playback (Barge-in).
        """
        logger.info("Pipeline interrupt triggered: %s", reason)
        if self._current_gen_task and not self._current_gen_task.done():
            self._current_gen_task.cancel()
            self._current_gen_task = None

        # Clear text and audio queues
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
                self.text_queue.task_done()
            except Exception:
                break

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except Exception:
                break

        # Stop TTS audio engine
        try:
            self.tts.stop()
        except Exception:
            pass

        self.chunker.reset()
        self.is_speaking = False

        bus = get_event_bus()
        bus.set_status(AgentStatus.ONLINE, "Listening")
        await self._emit_event({
            "type": "interrupted",
            "reason": reason,
            "timestamp": time.time(),
        })

    async def _emit_event(self, event: Dict[str, Any]) -> None:
        """Deliver event to registered callback and global event bus."""
        if self.event_callback:
            try:
                res = self.event_callback(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug("Error in event_callback: %s", e)

    async def process_user_audio(self, audio_bytes: bytes) -> None:
        """
        Full end-to-end voice turn from recorded speech:
        1. STT Transcribe
        2. Stream response
        """
        self.metrics = PipelineLatencyMetrics()
        self.metrics.user_speech_final_ts = time.time()

        await self._emit_event({"type": "stt_start"})
        bus = get_event_bus()
        bus.set_status(AgentStatus.TRANSCRIBING, "Transcribing speech...")

        try:
            stt_res = await self.stt.transcribe(audio_bytes)
            transcript = stt_res.text.strip()
            self.metrics.stt_completed_ts = time.time()
        except Exception as exc:
            logger.error("STT error in pipeline: %s", exc)
            await self._emit_event({"type": "error", "message": f"STT failed: {exc}"})
            bus.set_status(AgentStatus.ONLINE, "Ready")
            return

        if not transcript:
            bus.set_status(AgentStatus.ONLINE, "Ready")
            return

        await self.process_text_prompt(transcript)

    async def process_text_prompt(self, user_prompt: str) -> None:
        """
        Process a user prompt (from STT or text) into streaming voice response.
        """
        prompt = user_prompt.strip()
        if not prompt:
            return

        # Check for barge-in / stop command
        from app.agent.fast_router import is_exit_command
        if is_exit_command(prompt):
            await self.interrupt("exit_command")
            await self._emit_event({
                "type": "transcript_final",
                "text": prompt,
            })
            await self._emit_event({
                "type": "assistant_done",
                "text": "Goodbye! Voice session ended.",
            })
            return

        await self._emit_event({
            "type": "transcript_final",
            "text": prompt,
        })

        # Cancel any previous in-flight generation
        if self._current_gen_task and not self._current_gen_task.done():
            self._current_gen_task.cancel()

        self._current_gen_task = asyncio.create_task(self._stream_pipeline(prompt))

    async def _stream_pipeline(self, prompt: str) -> None:
        """Execute the streaming generator -> text queue."""
        self.metrics.llm_request_ts = time.time()
        bus = get_event_bus()
        bus.set_status(AgentStatus.THINKING, "Thinking...")

        await self._emit_event({"type": "llm_start"})
        self.chunker.reset()

        full_response_parts: List[str] = []
        first_token = True

        # ── 1. Check Fast Router (0ms LLM bypass) ─────────────────────────────
        fast_route = FastRouter.match(prompt)
        if fast_route.matched:
            # Immediate response
            reply_text = fast_route.direct_response
            if fast_route.tool_name:
                from app.agent.agent import build_agent
                from app.agent.base import AgentInput
                agent = build_agent()
                out = await agent.run(AgentInput(command=prompt))
                reply_text = out.response

            reply = reply_text or fast_route.conversational_prefix or "Done."
            self.metrics.llm_first_token_ts = time.time()
            self.metrics.chunker_first_sentence_ts = time.time()

            await self._emit_event({"type": "llm_chunk", "text": reply})
            await self.text_queue.put(reply)
            await self.text_queue.put(None)  # EOF marker for this turn
            self.conv_mgr.add_user_message(prompt)
            self.conv_mgr.add_assistant_message(reply)
            return

        # ── 2. Streaming LLM via Groq ─────────────────────────────────────────
        messages = self.conv_mgr.get_messages(current_prompt=prompt)
        try:
            async for token in self.groq.stream_chat_completion(messages):
                if first_token:
                    self.metrics.llm_first_token_ts = time.time()
                    first_token = False

                full_response_parts.append(token)
                await self._emit_event({"type": "llm_chunk", "text": token})

                ready_chunks = self.chunker.add_token(token)
                for c in ready_chunks:
                    if not self.metrics.chunker_first_sentence_ts:
                        self.metrics.chunker_first_sentence_ts = time.time()
                    await self.text_queue.put(c)

            # Flush trailing remainder
            final_chunk = self.chunker.flush()
            if final_chunk:
                if not self.metrics.chunker_first_sentence_ts:
                    self.metrics.chunker_first_sentence_ts = time.time()
                await self.text_queue.put(final_chunk)

            # Send EOF marker to text queue for this turn
            await self.text_queue.put(None)

            complete_text = "".join(full_response_parts)
            self.conv_mgr.add_user_message(prompt)
            self.conv_mgr.add_assistant_message(complete_text)

        except asyncio.CancelledError:
            logger.debug("Streaming pipeline task cancelled.")
            raise
        except Exception as exc:
            logger.error("Streaming LLM error: %s", exc)
            fallback = "I apologize, but I encountered an issue generating that response."
            await self.text_queue.put(fallback)
            await self.text_queue.put(None)

    async def _tts_worker(self) -> None:
        """
        TTS Worker loop:
        Consumes text chunks from text_queue, synthesizes audio chunks,
        and pushes them into audio_queue.
        """
        chunk_idx = 0
        while self.is_active:
            try:
                text_chunk = await self.text_queue.get()
                if text_chunk is None:
                    # End of current turn
                    await self.audio_queue.put(None)
                    self.text_queue.task_done()
                    chunk_idx = 0
                    continue

                if not self.metrics.tts_first_audio_ts:
                    self.metrics.tts_first_audio_ts = time.time()

                await self._emit_event({
                    "type": "tts_start",
                    "chunk_index": chunk_idx,
                    "text": text_chunk,
                })

                # Synthesize audio bytes
                audio_bytes = await self.tts.synthesize(text_chunk)
                item = AudioQueueItem(
                    chunk_index=chunk_idx,
                    text=text_chunk,
                    audio_bytes=audio_bytes,
                )
                await self.audio_queue.put(item)
                chunk_idx += 1
                self.text_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("TTS worker error: %s", e)

    async def _playback_worker(self) -> None:
        """
        Playback Worker loop:
        Consumes audio chunks from audio_queue and either:
        1. Plays them through host speakers (System TTS / SAPI)
        2. Streams them to the WebSocket client as base64 audio chunks
        """
        bus = get_event_bus()
        while self.is_active:
            try:
                item = await self.audio_queue.get()
                if item is None:
                    # Turn complete!
                    self.is_speaking = False
                    bus.set_status(AgentStatus.ONLINE, "Ready")
                    ttfa = self.metrics.time_to_first_audio_ms
                    logger.info(
                        "[VOICE METRICS] TTFA: %0.1fms | STT: %0.1fms | LLM: %0.1fms | TTS: %0.1fms",
                        ttfa,
                        self.metrics.stt_latency_ms,
                        self.metrics.llm_first_token_ms,
                        self.metrics.tts_first_audio_ms,
                    )
                    await self._emit_event({
                        "type": "assistant_done",
                        "metrics": self.metrics.to_dict(),
                    })
                    self.audio_queue.task_done()
                    continue

                if not self.is_speaking:
                    self.is_speaking = True
                    self.metrics.playback_start_ts = time.time()
                    bus.set_status(AgentStatus.SPEAKING, "Speaking response...")

                # Emit audio chunk to WebSocket client
                b64_data = base64.b64encode(item.audio_bytes).decode("ascii") if item.audio_bytes else ""
                await self._emit_event({
                    "type": "audio_chunk",
                    "chunk_index": item.chunk_index,
                    "text": item.text,
                    "data": b64_data,
                })

                # If host playback is enabled and audio exists or provider speaks synchronously
                if self.enable_host_playback:
                    try:
                        await self.tts.speak(item.text)
                    except Exception as e:
                        logger.debug("Host playback notice: %s", e)

                self.audio_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Playback worker error: %s", e)
