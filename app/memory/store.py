"""
Memory store — interface + in-memory implementation.

The interface is designed so a Redis-backed implementation can be
dropped in later without touching any caller code.
"""
from __future__ import annotations

import abc
import asyncio
import time
from typing import Any


class AbstractMemoryStore(abc.ABC):
    """Key-value store interface for agent short-term memory."""

    @abc.abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return the value for *key*, or None if not found / expired."""
        ...

    @abc.abstractmethod
    async def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        """
        Store *value* under *key*.

        Args:
            key:   Storage key.
            value: Any JSON-serialisable value.
            ttl:   Optional time-to-live in seconds.
        """
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove *key* from the store."""
        ...

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if *key* exists and has not expired."""
        ...

    @abc.abstractmethod
    async def list_all(self) -> dict[str, Any]:
        """Return all active key-value pairs."""
        ...

    @abc.abstractmethod
    async def clear(self) -> None:
        """Remove all entries."""
        ...


class InMemoryStore(AbstractMemoryStore):
    """
    Simple in-process dictionary store with optional TTL support.
    Thread-safe for asyncio single-thread usage.
    Production replacement: RedisStore (same interface).
    """

    def __init__(self) -> None:
        # { key: (value, expires_at_or_None) }
        self._data: dict[str, tuple[Any, float | None]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._data[key]
            return None
        return value

    async def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        expires_at = (time.monotonic() + ttl) if ttl is not None else None
        self._data[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def list_all(self) -> dict[str, Any]:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._data.items() if exp is not None and now > exp]
        for k in expired:
            del self._data[k]
        return {k: val for k, (val, _) in self._data.items()}

    async def clear(self) -> None:
        self._data.clear()


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: AbstractMemoryStore | None = None


def get_memory_store() -> AbstractMemoryStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store
