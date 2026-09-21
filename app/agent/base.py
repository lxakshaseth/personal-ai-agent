"""
Abstract Agent interface.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInput:
    """Represents a command sent to the agent."""

    command: str
    """Natural-language instruction from the user."""

    confirmed: bool = False
    """Whether the user has pre-confirmed high-risk actions."""

    session_id: str | None = None
    """Optional session identifier for memory/context continuity."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Arbitrary extra metadata (e.g. source: 'voice' | 'api' | 'cli')."""


@dataclass
class AgentOutput:
    """Represents the agent's response after executing a command."""

    success: bool
    """Overall success flag."""

    response: str
    """Human-readable summary of what the agent did."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """Ordered list of tool invocations with their results."""

    error: str | None = None
    """Error message if success=False."""

    should_speak: bool = True
    """Whether this response should be spoken aloud by VoiceResponseService."""

    mode: str = "COMMAND"
    """Execution mode: 'CHAT', 'COMMAND', or 'TASK'."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional response metadata."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "should_speak": self.should_speak,
            "mode": self.mode,
            "metadata": self.metadata,
        }


class AbstractAgent(abc.ABC):
    """
    Top-level agent interface.

    Concrete implementations inject a planner, executor, and any services
    they need.  Callers only interact with `run()`.
    """

    @abc.abstractmethod
    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """
        Process a natural-language command end-to-end.

        Args:
            agent_input: Structured input with command and session context.

        Returns:
            AgentOutput with execution results.
        """
        ...

    @abc.abstractmethod
    async def startup(self) -> None:
        """Called once at application startup to warm up resources."""
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Called once at application shutdown to release resources."""
        ...
