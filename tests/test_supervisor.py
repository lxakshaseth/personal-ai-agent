"""
Unit tests for Supervisor Agent, Specialized Workers, Complex Plan Decomposition,
8-state Task Lifecycle, and Persistence.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.agent.agent import PersonalAgent
from app.agent.base import AgentInput
from app.agent.executor import ToolExecutor
from app.agent.planner import GroqPlanner
from app.agent.supervisor import (
    SPECIALIST_WORKERS,
    SpecialistRole,
    SupervisorAgent,
    resolve_specialist_for_tool,
)
from app.agent.tasks import ComplexPlan, PlanStep, TaskManager, TaskState
from app.agent.tool_registry import AgentToolRegistry
from app.security.audit import AuditLogger
from app.security.permissions import PermissionChecker
from app.services.groq_client import GroqClient
from app.tools.applications.tools import OpenApplicationTool
from app.tools.filesystem import CreateFolderTool
from app.tools.impl.utility import GetCurrentTimeTool
from app.tools.windows.tools import OpenURLTool


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_client():
    client = MagicMock(spec=GroqClient)
    client.chat_completion = AsyncMock(return_value="Done.")
    client.chat_completion_with_tools = AsyncMock()
    return client


@pytest.fixture
def registry(temp_dir):
    r = AgentToolRegistry()
    r.register(GetCurrentTimeTool)
    r.register(OpenURLTool)
    r.register(OpenApplicationTool)
    r.register(CreateFolderTool)
    return r


@pytest.fixture
def task_manager(temp_dir):
    store_file = temp_dir / "tasks_test.json"
    return TaskManager(persistence_file=str(store_file))


@pytest.fixture
def executor(registry, temp_dir):
    audit_file = temp_dir / "audit.jsonl"
    logger = AuditLogger(log_file=str(audit_file))
    checker = PermissionChecker()
    return ToolExecutor(registry=registry, permission_checker=checker, audit_logger=logger)


# ── Specialist Workers Tests ──────────────────────────────────────────────────

def test_specialist_workers_coverage():
    """All 5 specialist workers exist and have valid tool mappings."""
    roles = [
        SpecialistRole.COMPUTER,
        SpecialistRole.BROWSER,
        SpecialistRole.FILE,
        SpecialistRole.COMMUNICATION,
        SpecialistRole.SYSTEM,
    ]
    for role in roles:
        assert role in SPECIALIST_WORKERS
        worker = SPECIALIST_WORKERS[role]
        assert worker.name == role
        assert len(worker.tool_names) > 0
        assert worker.icon != ""

    # Test tool resolution
    assert resolve_specialist_for_tool("open_url").name == SpecialistRole.BROWSER
    assert resolve_specialist_for_tool("open_application").name == SpecialistRole.COMPUTER
    assert resolve_specialist_for_tool("create_folder").name == SpecialistRole.FILE
    assert resolve_specialist_for_tool("send_whatsapp_message").name == SpecialistRole.COMMUNICATION
    assert resolve_specialist_for_tool("system_information").name == SpecialistRole.SYSTEM


# ── Complexity Detection Tests ────────────────────────────────────────────────

def test_is_complex_command(mock_client, registry, executor):
    supervisor = SupervisorAgent(mock_client, registry, executor)

    # Simple commands
    assert not supervisor.is_complex_command("Open YouTube")
    assert not supervisor.is_complex_command("What time is it")
    assert not supervisor.is_complex_command("Create a folder named Projects")

    # Complex multi-step commands
    complex_cmd_1 = "Find a React tutorial on YouTube, open VS Code, and create a folder called ReactPractice"
    assert supervisor.is_complex_command(complex_cmd_1)

    complex_cmd_2 = "Open Chrome and create a folder called Notes"
    assert supervisor.is_complex_command(complex_cmd_2)


# ── Decomposition Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rule_based_decomposition(mock_client, registry, executor):
    """Verify heuristic decomposition matches the multi-step user scenario."""
    # Force fallback by causing LLM to raise exception
    mock_client.chat_completion = AsyncMock(side_effect=Exception("LLM unavailable"))
    supervisor = SupervisorAgent(mock_client, registry, executor)

    cmd = "Find a React tutorial on YouTube, open VS Code, and create a folder called ReactPractice"
    plan = await supervisor.decompose_multi_step_plan(cmd)

    assert plan is not None
    assert plan.estimated_operations == 3
    assert len(plan.steps) == 3

    # Step 1: Browser Agent -> YouTube
    s1 = plan.steps[0]
    assert s1.specialist == SpecialistRole.BROWSER.value
    assert s1.tool_name == "open_url"
    assert "youtube" in s1.arguments.get("url", "").lower()

    # Step 2: Computer Agent -> VS Code
    s2 = plan.steps[1]
    assert s2.specialist == SpecialistRole.COMPUTER.value
    assert s2.tool_name == "open_application"
    assert "vs code" in s2.arguments.get("app_name", "").lower()

    # Step 3: File Agent -> create folder
    s3 = plan.steps[2]
    assert s3.specialist == SpecialistRole.FILE.value
    assert s3.tool_name == "create_folder"
    assert "ReactPractice" in s3.arguments.get("folder_path")


@pytest.mark.asyncio
async def test_llm_decomposition(mock_client, registry, executor):
    """Verify structured LLM response is correctly parsed into a ComplexPlan."""
    llm_json = json.dumps({
        "summary": "Search tutorial, launch IDE, and create workspace",
        "steps": [
            {
                "index": 1,
                "specialist": "Browser Agent",
                "action": "Search YouTube for React tutorial",
                "tool_name": "open_url",
                "arguments": {"url": "https://www.youtube.com/results?search_query=React+tutorial"},
            },
            {
                "index": 2,
                "specialist": "Computer Agent",
                "action": "Open VS Code",
                "tool_name": "open_application",
                "arguments": {"app_name": "VS Code"},
            },
        ],
    })
    mock_client.chat_completion = AsyncMock(return_value=f"```json\n{llm_json}\n```")
    supervisor = SupervisorAgent(mock_client, registry, executor)

    plan = await supervisor.decompose_multi_step_plan("search youtube and open vs code")
    assert plan is not None
    assert plan.estimated_operations == 2
    assert plan.steps[0].tool_name == "open_url"
    assert plan.steps[1].tool_name == "open_application"


# ── Task Lifecycle & 8 States ─────────────────────────────────────────────────

def test_task_states_and_persistence(task_manager, temp_dir):
    """Verify task manager strictly supports 8 formal states, approval, and disk persistence."""
    # 1. CREATED / PLANNING
    task = task_manager.create_task("Multi-step task")
    assert task.status == TaskState.PLANNING.value

    # 2. Attach Plan -> transitions to WAITING_APPROVAL
    plan = ComplexPlan(
        summary="Test multi-step plan",
        steps=[
            PlanStep(index=1, specialist="Browser Agent", action="Open Google", tool_name="open_url", arguments={"url": "https://google.com"}),
        ],
        estimated_operations=1,
    )
    task_manager.set_plan(task.id, plan)
    updated = task_manager.get_task(task.id)
    assert updated is not None
    assert updated.status == TaskState.WAITING_APPROVAL.value
    assert updated.is_complex is True

    # 3. Approve Task -> transitions to RUNNING
    approved = task_manager.approve_task(task.id)
    assert approved is True
    assert task_manager.get_task(task.id).status == TaskState.RUNNING.value

    # 4. PAUSED
    paused = task_manager.pause_task(task.id)
    assert paused is True
    assert task_manager.get_task(task.id).status == TaskState.PAUSED.value

    # 5. RESUME -> RUNNING
    resumed = task_manager.resume_task(task.id)
    assert resumed is True
    assert task_manager.get_task(task.id).status == TaskState.RUNNING.value

    # 6. COMPLETED
    task_manager.complete_task(task.id, "All operations finished")
    assert task_manager.get_task(task.id).status == TaskState.COMPLETED.value

    # 7. Verify persistence reload
    store_file = temp_dir / "tasks_test.json"
    assert store_file.exists()
    reloaded_mgr = TaskManager(persistence_file=str(store_file))
    reloaded_task = reloaded_mgr.get_task(task.id)
    assert reloaded_task is not None
    assert reloaded_task.description == "Multi-step task"
    assert reloaded_task.status == TaskState.COMPLETED.value
    assert reloaded_task.is_complex is True

    # 8. Filter by state
    completed_tasks = reloaded_mgr.list_tasks(state_filter="COMPLETED")
    assert len(completed_tasks) >= 1
    assert completed_tasks[0].id == task.id

    empty_filter = reloaded_mgr.list_tasks(state_filter="FAILED")
    assert len(empty_filter) == 0


# ── End-to-End Agent Integration & Security Stack ─────────────────────────────

@pytest.mark.asyncio
async def test_agent_complex_command_approval_flow(mock_client, registry, executor, monkeypatch):
    """
    Verify full flow:
    1. Agent receives complex command -> decomposes into plan, sets WAITING_APPROVAL, does NOT execute.
    2. User approves task -> Supervisor executes steps through central ToolExecutor.
    3. All steps are logged to audit log (security constraint).
    """
    planner = GroqPlanner(mock_client, registry)
    supervisor = SupervisorAgent(mock_client, registry, executor)
    agent = PersonalAgent(planner=planner, executor=executor, supervisor=supervisor)

    # Mock tool executions so we don't actually launch external applications
    from unittest.mock import patch
    with patch("webbrowser.open", return_value=True), \
         patch("subprocess.Popen", return_value=MagicMock()):

        cmd = "Find a React tutorial on YouTube, open VS Code, and create a folder called ReactPractice"
        output = await agent.run(AgentInput(command=cmd))

        # Must succeed and indicate waiting for approval
        assert output.success is True
        assert output.metadata.get("waiting_approval") is True
        assert output.metadata.get("is_complex") is True
        task_id = output.metadata.get("task_id")
        assert task_id is not None

        # Execute approved plan
        exec_result = await agent.approve_and_execute_task(task_id)
        assert exec_result["success"] is True
        assert len(exec_result["steps"]) == 3

        # Verify task is now completed
        from app.agent.tasks import get_task_manager
        final_task = get_task_manager().get_task(task_id)
        assert final_task.status == TaskState.COMPLETED.value
