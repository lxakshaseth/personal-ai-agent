"""
Async Circuit Breaker implementation for external service calls (e.g. Groq API).
Prevents cascading failures and resource exhaustion during downstream service outages.
"""
from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"          # Normal operation: requests pass through
    OPEN = "OPEN"              # Outage detected: requests fail fast
    HALF_OPEN = "HALF_OPEN"    # Testing recovery: probe request allowed


class CircuitBreakerOpenError(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""

    def __init__(self, service_name: str, retry_after: float) -> None:
        super().__init__(
            f"Circuit breaker for service '{service_name}' is OPEN. "
            f"Downstream service is temporarily unavailable. Retry after {retry_after:.1f}s."
        )
        self.service_name = service_name
        self.retry_after = retry_after


class CircuitBreaker:
    """
    State machine for protecting calls to remote services.

    Transitions:
      CLOSED --(failure_threshold failures)--> OPEN
      OPEN   --(cooldown_seconds elapsed)-----> HALF_OPEN
      HALF_OPEN --(successful probe)----------> CLOSED
      HALF_OPEN --(failed probe)--------------> OPEN
    """

    def __init__(
        self,
        service_name: str = "remote_service",
        failure_threshold: int = 5,
        cooldown_seconds: float = 20.0,
        success_threshold: int = 1,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        now = time.time()
        if self._state == CircuitState.OPEN:
            if now - self._last_failure_time >= self.cooldown_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def is_available(self) -> bool:
        """Return True if a request is allowed to proceed."""
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                return False
            return True

    async def record_success(self) -> None:
        """Record a successful execution."""
        async with self._lock:
            current = self.state
            if current == CircuitState.HALF_OPEN:
                self._consecutive_successes += 1
                if self._consecutive_successes >= self.success_threshold:
                    logger.info("CircuitBreaker[%s]: Probe succeeded. Transitioning to CLOSED.", self.service_name)
                    self._state = CircuitState.CLOSED
                    self._consecutive_failures = 0
                    self._consecutive_successes = 0
            elif current == CircuitState.CLOSED:
                self._consecutive_failures = 0

    async def record_failure(self, exc: Exception | None = None) -> None:
        """Record a failed execution."""
        async with self._lock:
            self._last_failure_time = time.time()
            current = self.state

            if current in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                self._state = CircuitState.OPEN
                logger.warning(
                    "CircuitBreaker[%s]: Failure in %s state. Keeping circuit OPEN for %0.1fs. Reason: %s",
                    self.service_name,
                    current.value,
                    self.cooldown_seconds,
                    exc,
                )
            elif current == CircuitState.CLOSED:
                self._consecutive_failures += 1
                if self._consecutive_failures >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(
                        "CircuitBreaker[%s]: Failure threshold reached (%d). Tripping circuit to OPEN for %0.1fs. Reason: %s",
                        self.service_name,
                        self._consecutive_failures,
                        self.cooldown_seconds,
                        exc,
                    )

    async def execute(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """Execute async function guarded by this circuit breaker."""
        async with self._lock:
            current = self.state
            if current == CircuitState.OPEN:
                retry_after = max(0.1, self.cooldown_seconds - (time.time() - self._last_failure_time))
                raise CircuitBreakerOpenError(self.service_name, retry_after)

        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as exc:
            await self.record_failure(exc)
            raise

    async def reset(self) -> None:
        """Manually reset the breaker to CLOSED state (useful for tests)."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._last_failure_time = 0.0
