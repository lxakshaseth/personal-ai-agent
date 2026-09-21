"""
Groq-backed LLM planner.

The planner:
  1. Builds a dynamic system prompt from the live tool registry.
  2. Calls the Groq API with function-calling enabled.
  3. Validates that the LLM only calls registered tools.
  4. Returns a PlannerResult (tool calls or plain-text reply).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.prompts import build_system_prompt
from app.agent.schemas import GroqErrorType
from app.agent.tool_registry import AgentToolRegistry
from app.services.groq_client import GroqClient
from app.utils.exceptions import PlannerError, ToolNotFoundError

logger = logging.getLogger(__name__)


# ── Plan data structures ───────────────────────────────────────────────────────

@dataclass
class ToolCallPlan:
    """A single tool invocation decided by the LLM planner."""

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannerResult:
    """Output from the planner: either tool calls or a plain-text reply."""

    tool_calls: list[ToolCallPlan] = field(default_factory=list)
    text_reply: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# ── Planner ────────────────────────────────────────────────────────────────────

class GroqPlanner:
    """
    Translates natural-language commands into tool calls via Groq function-calling.

    Injected dependencies:
        groq_client  – GroqClient instance (read-only, async)
        registry     – AgentToolRegistry (read-only at planning time)
    """

    def __init__(
        self,
        groq_client: GroqClient,
        registry: AgentToolRegistry,
    ) -> None:
        self._client = groq_client
        self._registry = registry

    async def plan(
        self,
        command: str,
        *,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> PlannerResult:
        """
        Decide which tool(s) to call for the given command.

        Flow:
          1. Build system prompt with live tool registry.
          2. Call Groq with function-calling enabled.
          3. Validate returned tool names against the registry.
          4. Return structured PlannerResult.

        Args:
            command:              The user's natural-language command.
            conversation_history: Optional prior messages for multi-turn context.

        Returns:
            PlannerResult with tool_calls or text_reply populated.

        Raises:
            PlannerError: On any Groq API failure (with groq_error attribute set).
        """
        # ── Build message list ─────────────────────────────────────────────────
        system_prompt = build_system_prompt(self._registry)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": command})

        # ── No tools registered — fall back to plain completion ────────────────
        tools = self._registry.function_specs()
        if not tools:
            logger.warning("No tools registered; using plain completion.")
            text = await self._client.chat_completion(messages)
            return PlannerResult(text_reply=text)

        # ── Groq function-calling ──────────────────────────────────────────────
        # PlannerError is re-raised from GroqClient on any API failure.
        try:
            message = await self._client.chat_completion_with_tools(messages, tools)
        except PlannerError as exc:
            if "timeout" in str(exc).lower():
                logger.warning("Planner function-calling timed out; falling back to plain chat completion...")
                try:
                    fallback_text = await self._client.chat_completion(messages, max_tokens=150)
                    return PlannerResult(text_reply=fallback_text)
                except Exception:
                    pass
            raise

        # ── Parse and validate tool calls ──────────────────────────────────────
        if message.tool_calls:
            plans: list[ToolCallPlan] = []
            for tc in message.tool_calls:
                tool_name = tc.function.name

                # Safety: reject any tool name not in the registry
                if tool_name not in self._registry:
                    logger.error(
                        "LLM requested unregistered tool %r — ignoring.", tool_name
                    )
                    raise PlannerError(
                        f"LLM requested an unregistered tool: {tool_name!r}. "
                        "This may indicate a prompt injection or a hallucinated tool name.",
                        detail=f"known tools: {self._registry.names()}",
                    )

                # Parse arguments
                try:
                    args = json.loads(tc.function.arguments)
                    if not isinstance(args, dict):
                        raise ValueError("arguments must be a JSON object")
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning(
                        "Failed to parse arguments for tool %r: %s — using {}",
                        tool_name,
                        exc,
                    )
                    args = {}

                plans.append(
                    ToolCallPlan(
                        tool_name=tool_name,
                        tool_call_id=tc.id,
                        arguments=args,
                    )
                )

            return PlannerResult(tool_calls=plans)

        # ── Plain-text reply (LLM chose not to call any tool) ─────────────────
        return PlannerResult(text_reply=message.content or "")

    async def synthesize_response(
        self,
        command: str,
        tool_results: list[dict[str, Any]],
    ) -> str:
        """
        Ask the LLM to compose a natural-language response from tool results.

        Called by PersonalAgent after tool execution to produce a friendly reply.
        Falls back to a simple template if the Groq call fails.
        """
        from app.agent.prompts import build_synthesis_prompt

        synthesis_prompt = build_synthesis_prompt(tool_results)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant summarising computer agent actions. "
                    "Be concise and friendly. One to three sentences maximum."
                ),
            },
            {"role": "user", "content": f"Original command: {command}\n\n{synthesis_prompt}"},
        ]
        try:
            fast_model = getattr(self._client, "fast_model", None)
            return await self._client.chat_completion(messages, model=fast_model, max_tokens=128)
        except Exception:
            # Fallback: build a plain summary without an LLM call
            parts = []
            for r in tool_results:
                status = "✓" if r.get("success") else "✗"
                parts.append(f"{status} {r.get('tool', '?')}: {r.get('output') or r.get('error', '')}")
            return "\n".join(parts)
