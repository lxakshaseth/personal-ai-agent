"""
Pydantic schemas for the agent layer.

These are the canonical request/response models used:
  - Between the API layer and the agent
  - For tool argument validation
  - For serialising execution results

Keeping schemas separate from business logic allows them to be imported
by any layer without circular dependencies.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Tool-layer schemas ─────────────────────────────────────────────────────────

class PermissionLevelSchema(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ToolResultSchema(BaseModel):
    """Serialisable form of a tool's execution result."""

    success: bool = Field(..., description="Whether the tool ran successfully")
    output: str = Field(..., description="Human-readable result text")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured output data")
    error: str | None = Field(default=None, description="Error message, if any")


class ToolCallSchema(BaseModel):
    """A single tool invocation record (returned in AgentResponse)."""

    tool: str = Field(..., description="Tool name")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments passed")
    success: bool = Field(..., description="Execution success flag")
    output: str = Field(default="", description="Tool output text")
    error: str | None = Field(default=None, description="Error message, if any")


class ToolInfoSchema(BaseModel):
    """Public metadata for a registered tool (used by GET /agent/tools)."""

    name: str
    description: str
    permission_level: PermissionLevelSchema
    requires_confirmation: bool = False
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


# ── Agent-layer schemas ────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    """Request body for POST /agent/run."""

    command: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language command for the agent",
    )
    confirmed: bool = Field(
        default=False,
        description="Set true to pre-confirm HIGH-risk tool execution",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for conversation continuity",
    )

    @model_validator(mode="after")
    def strip_command(self) -> "AgentRunRequest":
        self.command = self.command.strip()
        return self


class AgentRunResponse(BaseModel):
    """Response body for POST /agent/run."""

    success: bool = Field(..., description="Overall agent run success")
    response: str = Field(..., description="Natural-language reply to the user")
    tool_calls: list[ToolCallSchema] = Field(
        default_factory=list,
        description="Ordered list of tool invocations with results",
    )
    error: str | None = Field(default=None, description="Top-level error, if any")
    session_id: str | None = Field(default=None, description="Echo of the session ID")


# ── Tool input validation helpers ──────────────────────────────────────────────

class CreateFolderInput(BaseModel):
    """Validated input for the create_folder tool."""

    path: str = Field(
        ...,
        min_length=3,
        description="Absolute path of the folder to create",
    )
    exist_ok: bool = Field(
        default=True,
        description="If true, do not error when the folder already exists",
    )


class DeleteFolderInput(BaseModel):
    """Validated input for the delete_folder tool."""

    folder_path: str = Field(
        ...,
        min_length=3,
        description="Absolute path of the folder to delete",
    )


class OpenApplicationInput(BaseModel):
    """Validated input for the open_application tool."""

    app_name: str = Field(
        ...,
        min_length=1,
        description="Name of the application or website to open",
    )


class OpenFolderInput(BaseModel):
    """Validated input for the open_folder tool."""

    folder_path: str = Field(
        ...,
        min_length=1,
        description="Absolute path or well-known folder name (downloads, desktop…)",
    )


class BrowserSearchInput(BaseModel):
    """Validated input for the browser_search tool."""

    site: str = Field(..., description="Site to search (youtube, google, github…)")
    query: str = Field(..., min_length=1, description="Search query")


class GetCurrentTimeInput(BaseModel):
    """Validated input for the get_current_time tool (no required fields)."""

    timezone: str = Field(
        default="local",
        description="Timezone name (e.g. 'UTC', 'Asia/Kolkata') or 'local'",
    )


# ── Groq error classification ──────────────────────────────────────────────────

class GroqErrorType(str, Enum):
    INVALID_API_KEY = "invalid_api_key"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    MALFORMED_RESPONSE = "malformed_response"
    UNKNOWN = "unknown"


class GroqErrorDetail(BaseModel):
    """Structured Groq error info attached to PlannerError exceptions."""

    error_type: GroqErrorType
    message: str
    retryable: bool = False
    status_code: int | None = None
