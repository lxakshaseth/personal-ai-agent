"""
Command execution history recorder for personal-ai-agent.
"""
from __future__ import annotations

import time
from typing import Any
from pydantic import BaseModel, Field


class CommandHistoryRecord(BaseModel):
    id: str
    timestamp: float = Field(default_factory=time.time)
    command: str
    success: bool
    response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0


class CommandHistoryStore:
    """Thread-safe ring buffer for user command history."""

    def __init__(self, max_records: int = 100) -> None:
        self._records: list[CommandHistoryRecord] = []
        self._max_records = max_records

    def add(self, record: CommandHistoryRecord) -> None:
        self._records.insert(0, record)
        if len(self._records) > self._max_records:
            self._records.pop()

    def all(self) -> list[CommandHistoryRecord]:
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()


# ── Global Singleton ─────────────────────────────────────────────────────────

_history_store: CommandHistoryStore | None = None


def get_command_history_store() -> CommandHistoryStore:
    global _history_store
    if _history_store is None:
        _history_store = CommandHistoryStore()
    return _history_store
