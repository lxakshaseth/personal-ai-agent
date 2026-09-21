"""
Tests for real-time visualization events, sensitive data sanitization, and task cancellation.
"""
import pytest
from app.utils.sanitizer import sanitize_payload, sanitize_text, REDACTED
from app.services.event_bus import EventBus
from app.agent.tasks import TaskManager, AgentTask


def test_sanitizer_redacts_sensitive_keys():
    payload = {
        "user": "Alice",
        "api_key": "gsk_test12345678901234567890",
        "secret_token": "my-secret-value",
        "nested": {
            "password": "super-secret-password",
            "normal_field": "hello world",
            "auth_header": "Bearer secret123",
        },
        "cookies": ["session=xyz123", "tracker=abc"],
        "logs": ["cookie: session=xyz123", "normal log line with Bearer abcdef1234567890"],
    }
    sanitized = sanitize_payload(payload)

    assert sanitized["user"] == "Alice"
    assert sanitized["api_key"] == REDACTED
    assert sanitized["secret_token"] == REDACTED
    assert sanitized["nested"]["password"] == REDACTED
    assert sanitized["nested"]["normal_field"] == "hello world"
    assert sanitized["nested"]["auth_header"] == REDACTED
    assert sanitized["cookies"] == REDACTED
    assert REDACTED in sanitized["logs"][0]
    assert REDACTED in sanitized["logs"][1]


def test_sanitizer_redacts_keys_in_text():
    raw_text = "Encountered error using gsk_abcdef12345678901234567890 on endpoint."
    cleaned = sanitize_text(raw_text)
    assert "gsk_" not in cleaned
    assert REDACTED in cleaned


def test_event_bus_publish_event():
    bus = EventBus()
    bus.publish_event(
        "tool.started",
        {
            "tool": "open_url",
            "request_id": "req-123",
            "arguments": {"url": "https://youtube.com", "api_key": "gsk_12345678901234567890"},
        },
    )

    events = bus.get_recent_events()
    assert len(events) >= 1
    last_event = events[-1]

    # Verify event format
    assert last_event["event"] == "tool.started"
    assert last_event["type"] == "tool.started"
    assert last_event["tool"] == "open_url"
    assert last_event["request_id"] == "req-123"
    assert "timestamp" in last_event
    assert last_event["arguments"]["api_key"] == REDACTED


def test_task_cancellation_manager():
    mgr = TaskManager()
    task = mgr.create_task("Download large file")
    assert task.status == "planning"
    assert not mgr.is_cancelled(task.id)

    cancelled = mgr.cancel_task(task.id)
    assert cancelled is True
    assert mgr.is_cancelled(task.id)
    assert mgr.get_task(task.id).status == "cancelled"

    # Subsequent cancellation attempt should return False
    assert mgr.cancel_task(task.id) is False


def test_cancel_active_task():
    mgr = TaskManager()
    task = mgr.create_task("Long running task")
    assert mgr.get_active_task().id == task.id

    assert mgr.cancel_active_task() is True
    assert mgr.is_cancelled(task.id)
    assert mgr.get_active_task() is None
