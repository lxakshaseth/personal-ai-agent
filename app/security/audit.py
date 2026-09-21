"""
Audit logger — append-only JSONL audit trail for every tool invocation.

Schema per record:
    timestamp    – ISO 8601 UTC
    user_command – original natural-language command
    tool         – tool name
    arguments    – dict of arguments passed
    permission   – permission level of the tool (LOW/MEDIUM/HIGH)
    result       – "success" | "failure" | "denied" | "confirmation_required"
    output       – tool output string (truncated to 2000 chars)
    error        – error message if result != "success"
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Max chars stored per output field to keep log files manageable
_MAX_OUTPUT_LEN = 2000


class AuditLogger:
    """Writes a structured JSONL record for every tool invocation."""

    def __init__(self, log_file: str | None = None) -> None:
        settings = get_settings()
        self._log_path = Path(log_file or settings.audit_log_file)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        command: str,
        tool_name: str,
        tool_args: dict[str, Any],
        success: bool,
        output: str,
        error: str | None = None,
        permission_level: str | None = None,
    ) -> None:
        """
        Append one audit record.

        Args:
            command:          Original user command.
            tool_name:        Name of the tool that was called.
            tool_args:        Arguments the tool received.
            success:          True if the tool executed successfully.
            output:           Tool output (truncated if very long).
            error:            Error message if success=False.
            permission_level: Tool's PermissionLevel value (LOW/MEDIUM/HIGH).
        """
        # Derive result label from success + error content
        if success:
            result = "success"
        elif error and "confirmation required" in error.lower():
            result = "confirmation_required"
        elif error and ("denied" in error.lower() or "outside allowed" in error.lower() or "protected" in error.lower()):
            result = "denied"
        else:
            result = "failure"

        record: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "user_command": command,
            "tool": tool_name,
            "arguments": tool_args,
            "permission": permission_level or "UNKNOWN",
            "result": result,
            "output": (output or "")[:_MAX_OUTPUT_LEN],
            "error": error,
        }

        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except OSError:
            logger.exception("Failed to write audit log record for tool %r", tool_name)


# ── Singleton ─────────────────────────────────────────────────────────────────

_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
