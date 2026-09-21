"""
Event bus for real-time WebSocket broadcasting of agent state, tool execution,
voice events, and confirmation requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.utils.sanitizer import sanitize_payload

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_CONFIRMATION = "waiting_confirmation"
    ERROR = "error"


class EventType(str, Enum):
    STATUS_CHANGED = "status_changed"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    CONFIRMATION_REQUESTED = "confirmation_requested"
    CONFIRMATION_RESOLVED = "confirmation_resolved"
    VOICE_EVENT = "voice_event"
    COMMAND_STARTED = "command_started"
    COMMAND_COMPLETED = "command_completed"
    SYSTEM_METRICS = "system_metrics"
    LOG_EMITTED = "log_emitted"


class EventBus:
    """In-memory pub/sub event bus with WebSocket connection management."""

    def __init__(self) -> None:
        self._subscribers: set[Any] = set()
        self._current_status: AgentStatus = AgentStatus.ONLINE
        self._status_detail: str = "Ready"
        self._history: list[dict[str, Any]] = []
        self._max_history = 300

    @property
    def current_status(self) -> AgentStatus:
        return self._current_status

    @property
    def status_detail(self) -> str:
        return self._status_detail

    def set_status(self, status: AgentStatus, detail: str = "") -> None:
        """Update current agent status and broadcast status change event."""
        self._current_status = status
        self._status_detail = detail or status.value.replace("_", " ").title()
        self.publish_event(
            EventType.STATUS_CHANGED.value,
            {
                "status": self._current_status.value,
                "detail": self._status_detail,
            },
        )

    def register_client(self, websocket: Any) -> None:
        """Register an active WebSocket client."""
        self._subscribers.add(websocket)
        logger.debug("Registered WS client. Active clients: %d", len(self._subscribers))

    def unregister_client(self, websocket: Any) -> None:
        """Unregister a disconnected WebSocket client."""
        self._subscribers.discard(websocket)
        logger.debug("Unregistered WS client. Active clients: %d", len(self._subscribers))

    def publish_event(self, event_name: str, payload: dict[str, Any]) -> None:
        """
        Broadcast a real-time event with top-level attributes matching:
        {
          "event": "tool.started",
          "tool": "open_url",
          "timestamp": "2026-09-21T14:31:04Z",
          "request_id": "...",
          ...
        }
        All sensitive credentials, API keys, and tokens are automatically redacted.
        """
        sanitized = sanitize_payload(payload) or {}
        iso_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        timestamp = sanitized.get("timestamp") or iso_ts

        message: dict[str, Any] = {
            "event": event_name,
            "type": event_name,
            "timestamp": timestamp,
            "request_id": sanitized.get("request_id"),
            **sanitized,
            "payload": sanitized,
        }

        # Keep in history for initial snapshot on reconnect
        self._history.append(message)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        if not self._subscribers:
            return

        json_str = json.dumps(message)
        dead_clients: list[Any] = []

        for ws in list(self._subscribers):
            try:
                asyncio.create_task(self._send_safe(ws, json_str))
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            self._subscribers.discard(ws)

    def publish(self, event_type: EventType | str, payload: dict[str, Any]) -> None:
        """Backward-compatible publish method."""
        event_name = event_type.value if isinstance(event_type, EventType) else str(event_type)
        self.publish_event(event_name, payload)

    async def _send_safe(self, ws: Any, data: str) -> None:
        try:
            await ws.send_text(data)
        except Exception:
            self._subscribers.discard(ws)

    def get_recent_events(self) -> list[dict[str, Any]]:
        return list(self._history)

    async def close_all(self) -> None:
        """Gracefully close all connected WebSocket subscribers."""
        for ws in list(self._subscribers):
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass
        self._subscribers.clear()


# ── Global Singleton ─────────────────────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
