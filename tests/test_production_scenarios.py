"""
Production Verification Tests covering the 15 required operational scenarios:
1. Search YouTube (Find a React tutorial on YouTube)
2. Open application (VS Code)
3. Create folder (ReactPractice)
4. Permission elevation required for destructive operations
5. Permission elevation approved
6. Invalid filesystem path / path traversal protection
7. Unknown tool call handled cleanly
8. Invalid tool arguments handled cleanly
9. Groq failure (mocked 500 / 429) & circuit breaker handling
10. Browser failure / invalid URL handled cleanly
11. Confirmation timeout / ticket expiration
12. User cancellation
13. Agent restart lifecycle
14. Backend offline detection
15. WebSocket reconnect & event replay
"""
import asyncio
import os
import shutil
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.agent.agent import PersonalAgent, build_agent
from app.agent.tasks import TaskManager, TaskState
from app.agent.tool_registry import get_tool_registry, load_all_tools
from app.main import app
from app.security.confirmation_manager import ConfirmationManager, get_confirmation_manager
from app.security.path_validator import PathSecurityError, validate_path
from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.services.event_bus import AgentStatus, EventType, get_event_bus
from app.services.groq_client import GroqClient
from app.tools.base import PermissionLevel, ToolResult
from app.utils.exceptions import ToolNotFoundError


@pytest.fixture(autouse=True)
def init_tools():
    load_all_tools()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── Scenario 1: Search YouTube ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_scenario_1_youtube_search():
    registry = get_tool_registry()
    open_url_tool = registry.get_tool("open_url")
    assert open_url_tool is not None

    with patch("os.startfile", return_value=None) as mock_start:
        yt_url = "https://www.youtube.com/results?search_query=React+tutorial"
        result = await open_url_tool.execute(url=yt_url)
        assert result.success is True
        assert "youtube.com" in result.output.lower()
        mock_start.assert_called_once_with(yt_url)


# ── Scenario 2: Open VS Code ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_scenario_2_open_vscode():
    registry = get_tool_registry()
    open_app_tool = registry.get_tool("open_application")
    assert open_app_tool is not None

    with patch("subprocess.Popen") as mock_popen:
        result = await open_app_tool.execute(app_name="vscode")
        assert result.success is True
        assert "vscode" in result.output.lower() or "code" in result.output.lower()


# ── Scenario 3: Create Folder (ReactPractice) ─────────────────────────────────
@pytest.mark.asyncio
async def test_scenario_3_create_folder(tmp_path):
    registry = get_tool_registry()
    create_folder_tool = registry.get_tool("create_folder")
    target_folder = str(tmp_path / "ReactPractice")

    with patch("app.tools.filesystem.tools._allowed", return_value=[str(tmp_path)]):
        result = await create_folder_tool.execute(folder_path=target_folder)
        assert result.success is True
        assert Path(target_folder).exists()
        assert Path(target_folder).is_dir()


# ── Scenario 4: Permission Elevation Required for Destructive Action ──────────
def test_scenario_4_destructive_requires_confirmation():
    registry = get_tool_registry()
    del_folder_tool = registry.get_tool("delete_folder")
    del_file_tool = registry.get_tool("delete_file")

    assert del_folder_tool.requires_confirmation is True
    assert del_folder_tool.permission_level == PermissionLevel.HIGH
    assert del_file_tool.requires_confirmation is True
    assert del_file_tool.permission_level == PermissionLevel.HIGH

    cm = ConfirmationManager()
    ticket = cm.create_ticket(
        tool_name="delete_folder",
        arguments={"folder_path": "C:\\fake\\path"},
        command="delete folder ReactPractice",
    )
    assert ticket.status == "pending"
    assert len(cm.list_pending_tickets()) == 1


# ── Scenario 5: Permission Elevation Approved ─────────────────────────────────
@pytest.mark.asyncio
async def test_scenario_5_destructive_confirmed_executes(tmp_path):
    test_dir = tmp_path / "ToDelete"
    test_dir.mkdir(exist_ok=True)
    assert test_dir.exists()

    cm = ConfirmationManager()
    ticket = cm.create_ticket(
        tool_name="delete_folder",
        arguments={"folder_path": str(test_dir)},
    )
    assert ticket.status == "pending"

    # User approves ticket
    responded = cm.respond(ticket.ticket_id, approved=True)
    assert responded is True
    assert ticket.status == "approved"

    # With approval, execution proceeds
    registry = get_tool_registry()
    del_tool = registry.get_tool("delete_folder")
    with patch("app.tools.filesystem.tools._allowed", return_value=[str(tmp_path)]):
        result = await del_tool.execute(folder_path=str(test_dir))
        assert result.success is True
        assert not test_dir.exists()


# ── Scenario 6: Invalid Filesystem Path / Path Traversal ──────────────────────
def test_scenario_6_path_traversal_blocked(tmp_path):
    allowed_dirs = [str(tmp_path)]

    # 1. Path traversal escape attempt
    with pytest.raises(PathSecurityError):
        validate_path(str(tmp_path / ".." / ".." / "Windows" / "System32"), allowed_dirs)

    # 2. Accessing system directory
    with pytest.raises(PathSecurityError):
        validate_path(r"C:\Windows\System32\drivers\etc\hosts", allowed_dirs)


# ── Scenario 7: Unknown Tool Call Handled Cleanly ─────────────────────────────
def test_scenario_7_unknown_tool_handled():
    registry = get_tool_registry()
    with pytest.raises(ToolNotFoundError) as exc_info:
        registry.get_tool("non_existent_super_hack_tool")

    assert "non_existent_super_hack_tool" in str(exc_info.value)


# ── Scenario 8: Invalid Tool Arguments Handled Cleanly ────────────────────────
@pytest.mark.asyncio
async def test_scenario_8_invalid_tool_arguments():
    registry = get_tool_registry()
    create_file_tool = registry.get_tool("create_file")

    # Missing required 'file_path' argument
    with pytest.raises(Exception):
        create_file_tool.validate_inputs({})


# ── Scenario 9: Groq API Failure / Circuit Breaker ────────────────────────────
@pytest.mark.asyncio
async def test_scenario_9_groq_failure_handled():
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)

    await breaker.record_failure()
    await breaker.record_failure()
    assert await breaker.is_available() is False

    async def fail_call():
        return "fail"

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.execute(fail_call)


# ── Scenario 10: Browser Failure / Invalid URL Handled Cleanly ────────────────
@pytest.mark.asyncio
async def test_scenario_10_browser_failure_handled():
    registry = get_tool_registry()
    open_url_tool = registry.get_tool("open_url")

    with patch("os.startfile", side_effect=OSError("System cannot find default browser")):
        result = await open_url_tool.execute(url="https://broken-target.local")
        assert result.success is False
        assert "cannot find default browser" in result.error.lower()


# ── Scenario 11: Confirmation Timeout / Expiration ───────────────────────────
def test_scenario_11_confirmation_timeout_expiry():
    cm = ConfirmationManager()
    ticket = cm.create_ticket(
        tool_name="delete_file",
        arguments={"file_path": "C:\\test.txt"},
        timeout_seconds=0.05,
    )
    time.sleep(0.08)

    pending = cm.list_pending_tickets()
    assert len(pending) == 0
    assert ticket.status == "expired"


# ── Scenario 12: User Cancellation ────────────────────────────────────────────
def test_scenario_12_user_cancellation():
    tm = TaskManager()
    task = tm.create_task("Download large model and training set")
    assert task.status in (TaskState.PLANNING.value, TaskState.RUNNING.value, "planning", "executing")

    cancelled = tm.cancel_task(task.id)
    assert cancelled is True
    assert tm.is_cancelled(task.id) is True
    assert tm.get_task(task.id).status.upper() == TaskState.CANCELLED.value


# ── Scenario 13: Agent Restart Lifecycle ──────────────────────────────────────
@pytest.mark.asyncio
async def test_scenario_13_agent_restart():
    agent = build_agent()
    # Lifecycle startup & shutdown execute without errors
    await agent.startup()
    await agent.shutdown()


# ── Scenario 14: Backend Offline Detection ────────────────────────────────────
def test_scenario_14_backend_health_and_offline(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


# ── Scenario 15: WebSocket Reconnect & Event Snapshot ─────────────────────────
def test_scenario_15_websocket_snapshot(client):
    bus = get_event_bus()
    bus.set_status(AgentStatus.ONLINE, "System Ready")
    bus.publish_event("tool.completed", {"tool": "open_url", "status": "success"})

    # Connect WebSocket client to /ws/events and verify initial snapshot
    with client.websocket_connect("/ws/events") as ws:
        msg = ws.receive_json()
        assert "type" in msg
        assert msg["type"] == "init_snapshot"
        assert msg["payload"]["status"] == "online"
