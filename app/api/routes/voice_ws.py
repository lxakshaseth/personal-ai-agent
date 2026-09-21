"""
Dedicated Streaming Voice WebSocket Endpoint (/ws/voice).
Provides a persistent, bi-directional full-duplex connection for real-time
conversational voice interactions, audio streaming, VAD state updates,
token-by-token LLM output, and instantaneous barge-in interruption.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.voice.streaming_pipeline import StreamingVoicePipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Voice WebSocket"])


@router.websocket("/ws/voice")
async def voice_streaming_endpoint(websocket: WebSocket) -> None:
    """
    Real-time streaming voice WebSocket.

    Protocol:
    Client -> Server (JSON or Binary):
      - Binary: 16kHz 16-bit Mono PCM audio chunks
      - JSON:
          {"type": "prompt", "text": "hello"}
          {"type": "interrupt"}
          {"type": "ping"}
          {"type": "get_state"}

    Server -> Client (JSON):
      - {"type": "vad_state", "state": "speaking" | "silence"}
      - {"type": "transcript_final", "text": "..."}
      - {"type": "llm_start"}
      - {"type": "llm_chunk", "text": "..."}
      - {"type": "tts_start", "chunk_index": 0}
      - {"type": "audio_chunk", "chunk_index": 0, "text": "...", "data": "base64..."}
      - {"type": "assistant_done", "metrics": {...}}
      - {"type": "interrupted"}
      - {"type": "state_machine", "state": "IDLE|LISTENING|PROCESSING|SPEAKING|INTERRUPTING|ERROR"}
      - {"type": "heartbeat"}
    """
    await websocket.accept()
    logger.info("Voice streaming WebSocket client connected.")

    async def send_event(event: Dict[str, Any]) -> None:
        try:
            await websocket.send_text(json.dumps(event))
        except Exception:
            pass

    # Initialize streaming pipeline
    pipeline = StreamingVoicePipeline(
        event_callback=send_event,
        enable_host_playback=False,  # Client UI handles playback over WS stream
    )
    await pipeline.start()

    # ── Heartbeat Task: Prevents NAT/proxy timeouts (Phase 24) ───────────────
    async def heartbeat_loop() -> None:
        """Send a lightweight ping every 25s to keep the WebSocket alive."""
        while True:
            await asyncio.sleep(25)
            try:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except Exception:
                break

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    try:
        # Initial greeting event
        await send_event({
            "type": "connection_ready",
            "message": "NOVA Real-Time Conversational Voice Engine Ready",
            "state": "IDLE",
        })

        while True:
            message = await websocket.receive()

            # ── Binary Frame: Incoming Mic PCM Audio ─────────────────────────
            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]
                vad_event, final_audio = pipeline.vad.process_chunk(pcm_data)

                if vad_event == "speech_start":
                    # If assistant is currently speaking and user starts talking -> BARGE IN!
                    if pipeline.is_speaking:
                        await send_event({"type": "state_machine", "state": "INTERRUPTING"})
                        await pipeline.interrupt("user_barge_in")

                    await send_event({"type": "vad_state", "state": "speaking"})
                    await send_event({"type": "state_machine", "state": "LISTENING"})

                elif vad_event == "speech_final" and final_audio:
                    await send_event({"type": "vad_state", "state": "silence"})
                    await send_event({"type": "state_machine", "state": "PROCESSING"})
                    # Dispatch to low-latency Whisper STT and streaming LLM
                    asyncio.create_task(pipeline.process_user_audio(final_audio))

            # ── Text Frame: JSON Control Messages ────────────────────────────
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = payload.get("type", "")

                if msg_type == "ping":
                    await send_event({"type": "pong"})

                elif msg_type in ("interrupt", "stop", "cancel"):
                    await send_event({"type": "state_machine", "state": "INTERRUPTING"})
                    await pipeline.interrupt("client_request")
                    await send_event({"type": "state_machine", "state": "IDLE"})

                elif msg_type == "prompt":
                    prompt_text = payload.get("text", "")
                    if prompt_text:
                        await send_event({"type": "state_machine", "state": "PROCESSING"})
                        asyncio.create_task(pipeline.process_text_prompt(prompt_text))

                elif msg_type == "clear_history":
                    pipeline.conv_mgr.clear()
                    await send_event({"type": "history_cleared"})

                elif msg_type == "get_state":
                    # Client can query current pipeline state on reconnect
                    state = "SPEAKING" if pipeline.is_speaking else "IDLE"
                    await send_event({"type": "state_machine", "state": state})

    except WebSocketDisconnect:
        logger.info("Voice streaming WebSocket client disconnected.")
    except Exception as exc:
        logger.warning("Voice streaming WebSocket exception: %s", exc)
        try:
            await send_event({"type": "state_machine", "state": "ERROR", "detail": str(exc)})
        except Exception:
            pass
    finally:
        heartbeat_task.cancel()
        await pipeline.stop()
