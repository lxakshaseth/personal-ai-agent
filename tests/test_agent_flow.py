"""
End-to-end unit tests for PersonalAgent, GroqPlanner, and ToolExecutor flow.

Verifies:
- Command intent understanding and tool selection (e.g. get_current_time)
- Invalid argument validation via Pydantic
- Unknown tool rejection
- Natural language response synthesis
- Confirmation requirement on dangerous tools
- Comprehensive Groq API failure scenarios (auth, rate limit, timeout, network, malformed)
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.agent.agent import PersonalAgent
from app.agent.base import AgentInput, AgentOutput
from app.agent.executor import ToolExecutor
from app.agent.planner import GroqPlanner, PlannerResult, ToolCallPlan
from app.agent.schemas import (
    GetCurrentTimeInput,
    GroqErrorDetail,
    GroqErrorType,
)
from app.agent.tool_registry import AgentToolRegistry
from app.security.audit import AuditLogger
from app.security.permissions import PermissionChecker
from app.services.groq_client import GroqClient
from app.tools.base import AbstractTool, PermissionLevel, ToolResult
from app.tools.impl.utility import GetCurrentTimeTool
from app.utils.exceptions import PlannerError


# ── Fixture: Agent with configured mock client ────────────────────────────────

@pytest.fixture
def mock_groq():
    client = MagicMock(spec=GroqClient)
    client.chat_completion = AsyncMock(return_value="The current time is 11:30 AM.")
    client.chat_completion_with_tools = AsyncMock()
    return client


@pytest.fixture
def registry():
    r = AgentToolRegistry()
    r.register(GetCurrentTimeTool)
    return r


import shutil
import tempfile
from pathlib import Path


@pytest.fixture(scope="module")
def _sandbox_root():
    base = Path(__file__).parent.parent / ".pytest_sandbox"
    base.mkdir(exist_ok=True)
    return base


@pytest.fixture
def sandbox(_sandbox_root):
    tmp = Path(tempfile.mkdtemp(dir=_sandbox_root))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def agent(mock_groq, registry, sandbox):
    permission_checker = PermissionChecker()
    audit_logger = AuditLogger(log_file=str(sandbox / "audit.jsonl"))
    planner = GroqPlanner(groq_client=mock_groq, registry=registry)
    executor = ToolExecutor(
        registry=registry,
        permission_checker=permission_checker,
        audit_logger=audit_logger,
    )
    return PersonalAgent(planner=planner, executor=executor)



# ── Tests: Tool Selection & Execution ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_tell_me_current_time_executes_tool(agent, mock_groq) -> None:
    """User asks 'Tell me the current time.' -> LLM selects get_current_time -> tool executes."""
    # Simulate Groq LLM returning function call for get_current_time
    mock_msg = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "get_current_time"
    mock_tool_call.function.arguments = json.dumps({"timezone": "UTC"})
    mock_msg.tool_calls = [mock_tool_call]
    mock_msg.content = None
    mock_groq.chat_completion_with_tools.return_value = mock_msg
    mock_groq.chat_completion.return_value = "It is currently 11:30 AM UTC."

    output = await agent.run(AgentInput(command="Tell me the current time."))

    assert output.success is True
    assert len(output.tool_calls) == 1
    assert output.tool_calls[0]["tool"] == "get_current_time"
    assert output.tool_calls[0]["success"] is True
    assert "UTC" in output.tool_calls[0]["output"]
    # Fast-path: single successful tool returns its raw output, no extra LLM call
    assert "UTC" in output.response  # The tool output contains the time with timezone


@pytest.mark.asyncio
async def test_plain_text_reply_when_no_tool_called(agent, mock_groq) -> None:
    """Conversational input with no matching tool -> returns direct text reply."""
    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = "Hello! I am your personal computer agent. How can I help you?"
    mock_groq.chat_completion_with_tools.return_value = mock_msg

    output = await agent.run(AgentInput(command="Hello who are you?"))

    assert output.success is True
    assert len(output.tool_calls) == 0
    assert "personal computer agent" in output.response


@pytest.mark.asyncio
async def test_empty_command_handled_gracefully(agent) -> None:
    output = await agent.run(AgentInput(command="   "))
    assert output.success is False
    assert "didn't receive a command" in output.response.lower()


# ── Tests: Safety & Validation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_tool_rejected(agent, mock_groq) -> None:
    """If LLM hallucinates an unregistered tool name, planner rejects it safely."""
    mock_msg = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_bad"
    mock_tool_call.function.name = "unregistered_dangerous_tool"
    mock_tool_call.function.arguments = "{}"
    mock_msg.tool_calls = [mock_tool_call]
    mock_groq.chat_completion_with_tools.return_value = mock_msg

    output = await agent.run(AgentInput(command="Do something unknown"))

    assert output.success is False
    assert "unregistered tool" in output.error.lower() or "planning failed" in output.response.lower()


@pytest.mark.asyncio
async def test_invalid_tool_arguments_rejected(registry, sandbox) -> None:
    """Pydantic model validates tool arguments; invalid inputs are rejected."""
    class StrictTool(AbstractTool):
        input_model = GetCurrentTimeInput
        @property
        def name(self): return "strict_tool"
        @property
        def description(self): return "Strict input tool"
        @property
        def permission_level(self): return PermissionLevel.LOW
        @property
        def parameters_schema(self): return {"type": "object", "properties": {"timezone": {"type": "string"}}}
        async def execute(self, **kwargs): return ToolResult(success=True, output="ok")

    registry.register(StrictTool)
    executor = ToolExecutor(
        registry=registry,
        permission_checker=PermissionChecker(),
        audit_logger=AuditLogger(log_file=str(sandbox / "audit.jsonl")),
    )

    # Pass invalid argument structure (e.g. integer where string is expected, or extra validation)
    record = await executor._execute_one(
        ToolCallPlan(tool_name="strict_tool", tool_call_id="1", arguments={"timezone": ["invalid_list"]}),
        command="test",
        confirmed=False,
    )
    assert record.result.success is False
    assert "invalid arguments" in (record.result.error or "").lower()


@pytest.mark.asyncio
async def test_high_risk_tool_requires_confirmation(registry, sandbox) -> None:
    """HIGH risk tools require confirmation flag or they are rejected."""
    class DangerTool(AbstractTool):
        @property
        def name(self): return "danger_tool"
        @property
        def description(self): return "Dangerous action"
        @property
        def permission_level(self): return PermissionLevel.HIGH
        @property
        def parameters_schema(self): return {"type": "object", "properties": {}}
        async def execute(self, **kwargs): return ToolResult(success=True, output="exploded")

    registry.register(DangerTool)
    checker = PermissionChecker()
    checker._settings.agent_require_confirmation = True
    executor = ToolExecutor(
        registry=registry,
        permission_checker=checker,
        audit_logger=AuditLogger(log_file=str(sandbox / "audit.jsonl")),
    )


    # Unconfirmed -> rejected
    unconfirmed_record = await executor._execute_one(
        ToolCallPlan(tool_name="danger_tool", tool_call_id="1", arguments={}),
        command="explode",
        confirmed=False,
    )
    assert unconfirmed_record.result.success is False
    assert "confirmation" in (unconfirmed_record.result.error or "").lower()

    # Confirmed -> runs successfully
    confirmed_record = await executor._execute_one(
        ToolCallPlan(tool_name="danger_tool", tool_call_id="2", arguments={}),
        command="explode",
        confirmed=True,
    )
    assert confirmed_record.result.success is True
    assert confirmed_record.result.output == "exploded"


# ── Tests: Groq API Error Handling ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_groq_invalid_api_key_error(agent, mock_groq) -> None:
    detail = GroqErrorDetail(
        error_type=GroqErrorType.INVALID_API_KEY,
        message="Invalid API key",
        status_code=401,
    )
    err = PlannerError("Auth failed", detail=detail.model_dump_json())
    err.groq_error = detail
    mock_groq.chat_completion_with_tools.side_effect = err

    output = await agent.run(AgentInput(command="What is the time?"))

    assert output.success is False
    assert "API key is invalid" in output.response
    assert output.metadata["error_type"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_groq_rate_limit_error(agent, mock_groq) -> None:
    detail = GroqErrorDetail(
        error_type=GroqErrorType.RATE_LIMIT,
        message="Rate limit exceeded",
        retryable=True,
        status_code=429,
    )
    err = PlannerError("Rate limit", detail=detail.model_dump_json())
    err.groq_error = detail
    mock_groq.chat_completion_with_tools.side_effect = err

    output = await agent.run(AgentInput(command="What is the time?"))

    assert output.success is False
    assert "rate-limited" in output.response
    assert output.metadata["retryable"] is True


@pytest.mark.asyncio
async def test_groq_timeout_error(agent, mock_groq) -> None:
    detail = GroqErrorDetail(
        error_type=GroqErrorType.TIMEOUT,
        message="Request timed out",
        retryable=True,
    )
    err = PlannerError("Timeout", detail=detail.model_dump_json())
    err.groq_error = detail
    mock_groq.chat_completion_with_tools.side_effect = err

    output = await agent.run(AgentInput(command="What is the time?"))

    assert output.success is False
    assert "took too long to respond" in output.response


@pytest.mark.asyncio
async def test_groq_network_error(agent, mock_groq) -> None:
    detail = GroqErrorDetail(
        error_type=GroqErrorType.NETWORK,
        message="Connection refused",
        retryable=True,
    )
    err = PlannerError("Network fail", detail=detail.model_dump_json())
    err.groq_error = detail
    mock_groq.chat_completion_with_tools.side_effect = err

    output = await agent.run(AgentInput(command="What is the time?"))

    assert output.success is False
    assert "network issue" in output.response


@pytest.mark.asyncio
async def test_groq_malformed_response_error(agent, mock_groq) -> None:
    detail = GroqErrorDetail(
        error_type=GroqErrorType.MALFORMED_RESPONSE,
        message="Unexpected schema",
        retryable=False,
    )
    err = PlannerError("Malformed", detail=detail.model_dump_json())
    err.groq_error = detail
    mock_groq.chat_completion_with_tools.side_effect = err

    output = await agent.run(AgentInput(command="What is the time?"))

    assert output.success is False
    assert "unexpected response" in output.response
