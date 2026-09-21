"""
Abstract Tool interface and PermissionLevel enum.

Every concrete tool must:
  1. Subclass AbstractTool
  2. Declare name, description, permission_level, and parameters_schema
  3. Implement async execute(**kwargs) -> ToolResult
  4. Register itself via @register_tool (handled by the registry)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionLevel(str, Enum):
    """Risk classification for tools.

    LOW    – read-only or trivially reversible actions (open folder, search)
    MEDIUM – creates resources, opens apps, runs scripts
    HIGH   – deletes files/folders, sends messages, executes arbitrary code
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class ToolResult:
    """Structured result returned by every tool."""

    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "data": self.data,
            "error": self.error,
        }


class AbstractTool(abc.ABC):
    """
    Base class for all agent tools.

    Subclasses are expected to be stateless (or at most, share read-only
    infrastructure like a Playwright browser context injected at construction).
    """

    # ── Class-level declarations ───────────────────────────────────────────────
    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique machine-readable tool name (snake_case)."""
        ...

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human/LLM-readable description of what this tool does."""
        ...

    @property
    @abc.abstractmethod
    def permission_level(self) -> PermissionLevel:
        """Risk level that determines whether confirmation is required."""
        ...

    @property
    @abc.abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """
        JSON Schema object describing the tool's parameters.
        Used to build the function-calling payload sent to the LLM.

        Example:
          {
              "type": "object",
              "properties": {
                  "app_name": {"type": "string", "description": "Name of the app"}
              },
              "required": ["app_name"]
          }
        """
        ...

    # ── Execution ──────────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool with the given arguments.

        Args:
            **kwargs: Arguments validated against parameters_schema.

        Returns:
            ToolResult with success flag, human-readable output, and optional data.
        """
        ...

    # ── Helpers ────────────────────────────────────────────────────────────────

    def to_function_spec(self) -> dict[str, Any]:
        """
        Build the OpenAI/Groq function-calling spec for this tool.
        This is what gets sent to the LLM as part of the tools list.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"permission={self.permission_level.value})"
        )
