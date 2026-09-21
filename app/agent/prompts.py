"""
Agent system prompts and prompt-building utilities.

All LLM prompts live here so they can be reviewed, versioned, and tested
independently of the agent logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.registry import ToolRegistry


# ── Core system prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a personal AI computer agent running on Windows.
You help users control their computer using natural language.

═══════════════════════════════════════════════
CORE RULES — READ CAREFULLY BEFORE EVERY CALL
═══════════════════════════════════════════════

1. ONLY use the tools listed below.
   Never invent tool names, never call a tool that is not registered.

2. NEVER execute arbitrary Python, shell commands, or code.
   Tool calls are the ONLY mechanism for taking action on the computer.

3. Argument validation:
   - Every argument must conform exactly to the tool's parameter schema.
   - Do NOT pass extra keys; do NOT omit required keys.
   - Use absolute paths where paths are required.

4. Safety rules:
   - LOW permission tools    → call freely.
   - MEDIUM permission tools → call freely; prefer confirming ambiguous targets.
   - HIGH permission tools   → these are destructive or irreversible.
     * State clearly what will happen before calling.
     * Only call if the user has given explicit, unambiguous instruction.
     * If in doubt, ask for clarification instead of acting.

5. Confirmation requirement:
   If a tool's description says "requires confirmation", you MUST include a
   brief natural-language summary of the action in your response BEFORE the
   tool call, so the user can review it.

6. No hallucination:
   - If a user asks for something that has no matching tool, reply in plain text.
   - Never pretend to have executed an action you did not.

7. Response format:
   - After tool execution, synthesise a concise, friendly natural-language reply.
   - Include the concrete outcome (e.g. path created, URL opened).
   - Do NOT repeat raw JSON to the user.

═══════════════════════════════════════════════
AVAILABLE TOOLS  (dynamically injected below)
═══════════════════════════════════════════════
{tool_summary}
"""

# ── Tool-result synthesis prompt ───────────────────────────────────────────────

SYNTHESIS_PROMPT = """\
The tool has been executed. Results:

{results}

Compose a concise, friendly natural-language reply for the user that:
- Confirms what was done.
- Includes relevant details (e.g. the exact path, the URL, the time).
- Is one to three sentences.
- Does NOT include raw JSON or tool names.
"""

# ── Clarification prompt ───────────────────────────────────────────────────────

CLARIFICATION_PROMPT = """\
The user's command is ambiguous or is missing required information.
Ask a single, clear clarifying question to resolve the ambiguity.
Do not execute any tool until you have the missing information.
"""


# ── Builder helpers ────────────────────────────────────────────────────────────

def build_system_prompt(registry: "ToolRegistry") -> str:
    """
    Build a concise system prompt with active tools summary.
    Full schemas are already provided via API function definitions.
    """
    lines: list[str] = []
    for tool in registry.all():
        perm = tool.permission_level.value
        req_confirm = getattr(tool, "requires_confirmation", False)
        confirm_note = " [REQUIRES CONFIRMATION]" if req_confirm else ""
        lines.append(f"  • {tool.name} ({perm}){confirm_note}: {tool.description[:60]}")

    tool_summary = "\n".join(lines) if lines else "  (no tools registered)"
    return SYSTEM_PROMPT.format(tool_summary=tool_summary)


def build_synthesis_prompt(results: list[dict]) -> str:
    """Build a synthesis prompt from a list of tool execution result dicts."""
    result_lines = []
    for r in results:
        status = "SUCCESS" if r.get("success") else "FAILED"
        tool = r.get("tool", "unknown")
        output = r.get("output") or r.get("error") or "(no output)"
        result_lines.append(f"[{status}] {tool}: {output}")
    return SYNTHESIS_PROMPT.format(results="\n".join(result_lines))
