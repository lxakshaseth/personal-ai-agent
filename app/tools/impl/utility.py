"""
Utility tools — stateless, zero-side-effect tools useful for testing
and general agent operation.

Registered tools:
  - get_current_time : Returns the current local and UTC time
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.agent.schemas import GetCurrentTimeInput
from app.agent.tool_registry import register_tool
from app.tools.base import AbstractTool, PermissionLevel, ToolResult


@register_tool
class GetCurrentTimeTool(AbstractTool):
    """Return the current time — used to verify tool-calling works end-to-end."""

    input_model = GetCurrentTimeInput

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return (
            "Get the current date and time. "
            "Use when the user asks 'what time is it', 'what's today's date', "
            "or any question about the current time."
        )

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.LOW

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "Timezone name (e.g. 'UTC', 'Asia/Kolkata', 'America/New_York') "
                        "or 'local' for the system timezone. Defaults to 'local'."
                    ),
                    "default": "local",
                }
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        tz_name: str = kwargs.get("timezone", "local").strip()

        try:
            if tz_name.lower() == "local":
                now = datetime.now().astimezone()
                tz_label = now.tzname() or "local"
            else:
                tz = ZoneInfo(tz_name)
                now = datetime.now(tz=tz)
                tz_label = tz_name
        except (ZoneInfoNotFoundError, Exception):
            # Fallback to UTC on unknown timezone
            now = datetime.now(tz=timezone.utc)
            tz_label = "UTC (fallback — unknown timezone)"

        formatted = now.strftime("%A, %B %d, %Y at %I:%M:%S %p")
        output = f"Current time ({tz_label}): {formatted}"

        return ToolResult(
            success=True,
            output=output,
            data={
                "iso": now.isoformat(),
                "timezone": tz_label,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": now.strftime("%A"),
            },
        )
