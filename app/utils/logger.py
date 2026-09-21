"""
Structured logging configuration.

Uses Python's standard `logging` module with a JSON-friendly formatter.
All modules should obtain loggers via `get_logger(__name__)`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import get_settings


class _JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        from app.api.middleware.request_id import get_request_id
        from app.utils.sanitizer import sanitize_payload

        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        req_id = get_request_id()
        if req_id:
            payload["request_id"] = req_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # Attach any extra fields added via `extra={}`
        for key, value in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "module", "msecs", "message", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "taskName",
            }:
                payload[key] = value
        
        sanitized = sanitize_payload(payload)
        return json.dumps(sanitized, default=str)


def configure_logging() -> None:
    """
    Configure the root logger once at application startup.
    Call this from the FastAPI lifespan handler.
    """
    settings = get_settings()

    # Ensure log directory exists
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.getLevelName(settings.log_level.value)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Console handler (human-readable in debug, JSON in production)
    if settings.debug:
        console_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        console_fmt = _JSONFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_fmt)
    root.addHandler(console_handler)

    # File handler — always JSON
    file_handler = logging.FileHandler(
        log_dir / "app.log", encoding="utf-8"
    )
    file_handler.setFormatter(_JSONFormatter())
    root.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in (
        "httpx",
        "httpcore",
        "uvicorn.access",
        "comtypes",
        "comtypes.client",
        "comtypes._comobject",
        "comtypes._vtbl",
        "pyttsx3",
        "asyncio",
        "watchfiles",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Import and call at module level."""
    return logging.getLogger(name)
