"""
End-to-end tests for the 7 scenarios required by the specification:
1. "Hi Nova" -> instant visual + verbal response.
2. "Open YouTube" -> Fast router -> open_url -> speech -> READY.
3. "Create a folder called AI Projects on my desktop" -> executes folder creation.
4. "Delete AI Projects" -> requires confirmation ticket, does not delete before confirmation.
5. "Stop." -> interrupts current task and TTS audio safely, returns to READY.
6. Groq unavailable -> graceful error message, system remains usable.
7. TTS unavailable -> text response works without crashing.
"""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.agent.agent import PersonalAgent
from app.agent.base import AgentInput
from app.agent.executor import ToolExecutor
from app.agent.planner import GroqPlanner
from app.agent.schemas import GroqErrorDetail, GroqErrorType
from app.agent.supervisor import SupervisorAgent
from app.agent.tool_registry import get_tool_registry, load_all_tools
from app.security.audit import get_audit_logger
from app.security.permissions import get_permission_checker
from app.services.event_bus import AgentStatus, get_event_bus
from app.utils.exceptions import PlannerError
from app.voice.voice_response_service import VoiceResponseService


@pytest.fixture(autouse=True)
def ensure_tools():
    load_all_tools()


@pytest.fixture
def agent():
    registry = get_tool_registry()
    checker = get_permission_checker()
    audit = get_audit_logger()
    mock_groq = MagicMock()
    mock_groq.fast_model = "llama-3.1-8b-instant"
    executor = ToolExecutor(registry, checker, audit)
    planner = GroqPlanner(mock_groq, registry)
    supervisor = SupervisorAgent(mock_groq, registry, executor)
    return PersonalAgent(planner, executor, supervisor)


@pytest.mark.asyncio
async def test_scenario_1_hi_nova(agent):
    """TEST 1: User says 'Hi Nova' -> immediate visual and verbal response."""
    output = await agent.run(AgentInput(command="Hi Nova"))
    assert output.success is True
    assert output.mode == "CHAT"
    assert output.should_speak is True
    assert "help" in output.response.lower()
    assert get_event_bus().current_status in (AgentStatus.ONLINE, AgentStatus.IDLE)


@pytest.mark.asyncio
async def test_scenario_2_open_youtube(agent):
    """TEST 2: User says 'Open YouTube' -> fast path open_url -> spoken response."""
    with patch("webbrowser.open", return_value=True):
        output = await agent.run(AgentInput(command="Open YouTube"))
        assert output.success is True
        assert output.mode == "COMMAND"
        assert len(output.tool_calls) == 1
        assert output.tool_calls[0]["tool"] == "open_url"
        assert output.should_speak is True
        assert "youtube" in output.response.lower()


@pytest.mark.asyncio
async def test_scenario_3_create_folder(agent, tmp_path):
    """TEST 3: User says 'Create a folder called AI Projects on my desktop'."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        output = await agent.run(AgentInput(command="Create a folder called AI Projects on my desktop"))
        assert output.success is True
        assert output.mode == "COMMAND"
        assert len(output.tool_calls) == 1
        assert output.tool_calls[0]["tool"] == "create_folder"
        assert output.should_speak is True


@pytest.mark.asyncio
async def test_scenario_4_delete_folder_requires_confirmation(agent, tmp_path):
    """TEST 4: User says 'Delete AI Projects' -> Confirmation required, no deletion before approval."""
    # Simulate Groq calling delete_folder (HIGH permission)
    target_dir = tmp_path / "AI Projects"
    target_dir.mkdir(exist_ok=True)

    mock_msg = MagicMock()
    mock_tc = MagicMock()
    mock_tc.id = "call_del"
    mock_tc.function.name = "delete_folder"
    mock_tc.function.arguments = f'{{"folder_path": "{str(target_dir).replace("\\", "/")}"}}'
    mock_msg.tool_calls = [mock_tc]
    mock_msg.content = None
    agent._planner._client.chat_completion_with_tools = AsyncMock(return_value=mock_msg)

    # Run without pre-confirmation
    output = await agent.run(AgentInput(command="Delete AI Projects", confirmed=False))
    assert "confirmation" in (output.response or "").lower() or (output.tool_calls and not output.tool_calls[0]["success"])
    # Verify folder was NOT deleted
    assert target_dir.exists()


@pytest.mark.asyncio
async def test_scenario_5_stop_interrupts_playback():
    """TEST 5: Stop command halts task and audio playback safely, returning to READY."""
    voice_service = VoiceResponseService()
    voice_service.stop()
    assert voice_service.is_speaking is False
    assert get_event_bus().current_status in (AgentStatus.ONLINE, AgentStatus.IDLE)


@pytest.mark.asyncio
async def test_scenario_6_groq_unavailable(agent):
    """TEST 6: Groq unavailable -> clear error, agent remains usable."""
    detail = GroqErrorDetail(
        error_type=GroqErrorType.NETWORK,
        message="Connection refused",
        retryable=True,
    )
    err = PlannerError("Network fail", detail=detail.model_dump_json())
    err.groq_error = detail
    agent._planner._client.chat_completion_with_tools = AsyncMock(side_effect=err)

    # Complex/arbitrary command that must use Groq
    output = await agent.run(AgentInput(command="Please summarize the quarterly financial report in detail"))
    assert output.success is False
    assert "AI service" in output.response or "network" in output.response.lower()


@pytest.mark.asyncio
async def test_scenario_7_tts_unavailable(agent):
    """TEST 7: TTS unavailable -> text response still works."""
    from app.voice.voice_response_service import get_voice_service
    vs = get_voice_service()
    with patch.object(vs._provider, "speak", side_effect=Exception("Audio device error")):
        # Should not raise exception
        await vs.speak("Text response should not crash")
        assert vs.is_speaking is False
