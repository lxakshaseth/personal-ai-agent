"""
Production resilience tests:
- Circuit breaker state machine and recovery
- Sliding window rate limiting and exemptions
- Request ID correlation via contextvars and headers
- Secret sanitization and masking in structured JSON logs
- Readiness probe (/ready) subsystem checks
"""
import asyncio
import json
import logging
import time
from starlette.testclient import TestClient

import pytest
from app.main import app
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState
from app.api.middleware.rate_limiter import InMemoryRateLimiter
from app.api.middleware.request_id import set_request_id
from app.utils.logger import _JSONFormatter
from app.utils.sanitizer import sanitize_text, sanitize_payload


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_circuit_breaker_lifecycle():
    """Verify CLOSED -> OPEN -> HALF_OPEN -> CLOSED state transitions."""
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.2, service_name="test_breaker")
    assert cb.state == CircuitState.CLOSED
    assert await cb.is_available() is True

    # 1. Trigger failures up to threshold
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure()
    # Now OPEN
    assert cb.state == CircuitState.OPEN
    assert await cb.is_available() is False

    async def dummy():
        return "fail"

    with pytest.raises(CircuitBreakerOpenError):
        await cb.execute(dummy)

    # 2. Wait for cooldown expiry -> transitions to HALF_OPEN
    time.sleep(0.25)
    assert cb.state == CircuitState.HALF_OPEN
    assert await cb.is_available() is True

    # 3. Successful probe call closes the circuit
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._consecutive_failures == 0


@pytest.mark.asyncio
async def test_rate_limiter_logic():
    """Verify sliding-window rate limiter blocks bursts and calculates wait time."""
    limiter = InMemoryRateLimiter(requests_per_minute=3, window_seconds=1.0)
    client_ip = "192.168.1.100"

    # First 3 requests allowed
    for _ in range(3):
        allowed, _ = await limiter.is_allowed(client_ip)
        assert allowed is True

    # 4th request rejected
    allowed, wait_time = await limiter.is_allowed(client_ip)
    assert allowed is False
    assert wait_time >= 0


def test_request_id_generation_and_propagation(client):
    """Verify request ID is generated when absent and preserved when provided."""
    # 1. Generated if omitted
    res = client.get("/health")
    assert res.status_code == 200
    req_id = res.headers.get("X-Request-ID")
    assert req_id is not None
    assert req_id.startswith("req_")

    # 2. Preserved if supplied
    custom_id = "test-custom-trace-uuid-12345"
    res2 = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res2.status_code == 200
    assert res2.headers.get("X-Request-ID") == custom_id


def test_json_logger_secret_redaction():
    """Verify that _JSONFormatter strips Groq keys, tokens, and sensitive dictionary keys."""
    formatter = _JSONFormatter()
    set_request_id("req_audit_test_123")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting using key gsk_abc12345678901234567890 and Bearer secret_token_value_xyz",
        args=(),
        exc_info=None,
    )
    # Add sensitive extra dict
    record.auth = {"api_key": "super_secret_groq_key", "password": "mypassword123", "normal": "public_data"}

    formatted = formatter.format(record)
    log_data = json.loads(formatted)

    # Validate request_id injected
    assert log_data["request_id"] == "req_audit_test_123"

    # Validate message redacted
    assert "gsk_abc12345678901234567890" not in log_data["message"]
    assert "[REDACTED]" in log_data["message"]
    assert "Bearer secret_token_value_xyz" not in log_data["message"]

    # Validate extra fields redacted
    assert log_data["auth"]["api_key"] == "[REDACTED]"
    assert log_data["auth"]["password"] == "[REDACTED]"
    assert log_data["auth"]["normal"] == "public_data"


def test_readiness_probe(client):
    """Verify /ready probe reports subsystem statuses and 200 OK when ready."""
    res = client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "checks" in data
    assert data["checks"]["tools"]["status"] == "ok"
    assert data["checks"]["tools"]["count"] >= 5
    assert data["checks"]["storage"]["status"] == "ok"
    assert data["checks"]["event_bus"]["status"] == "ok"
