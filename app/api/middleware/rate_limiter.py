"""
Sliding-window in-memory rate limiting middleware for FastAPI.
Protects local API endpoints against runaway loops and accidental spam.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class InMemoryRateLimiter:
    """Sliding-window rate limiter tracking timestamps per IP address."""

    def __init__(self, requests_per_minute: int = 120, window_seconds: float = 60.0) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        """
        Check if client_ip is within the rate limit.
        Returns (is_allowed, retry_after_seconds).
        """
        now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            timestamps = self._history[client_ip]
            # Prune old timestamps
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.requests_per_minute:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                return False, retry_after

            timestamps.append(now)
            return True, 0

    async def reset(self) -> None:
        """Clear all rate limiting state (useful for tests)."""
        async with self._lock:
            self._history.clear()


# Default limiter instance
_default_limiter = InMemoryRateLimiter(requests_per_minute=120, window_seconds=60.0)


def get_rate_limiter() -> InMemoryRateLimiter:
    return _default_limiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware applying sliding-window rate limiting per client IP.
    Exempts health checks, documentation, and WebSocket connections.
    """

    def __init__(self, app, limiter: InMemoryRateLimiter | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter or _default_limiter
        self._exempt_paths = {
            "/health",
            "/ready",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in self._exempt_paths or path.startswith("/ws"):
            return await call_next(request)

        client_host = request.client.host if request.client else "127.0.0.1"
        allowed, retry_after = await self._limiter.is_allowed(client_host)

        if not allowed:
            req_id = getattr(request.state, "request_id", "unknown")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Too many requests. Please slow down and try again in {retry_after} seconds.",
                    "request_id": req_id,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-Request-ID": req_id,
                },
            )

        return await call_next(request)
