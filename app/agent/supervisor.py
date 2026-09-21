"""
Supervisor Agent & Specialized Workers Architecture for Multi-Step Workflows.

Architecture:
  Supervisor Agent
  │
  ├── Computer Agent       (open_app, close_app, lock_computer, screenshot)
  ├── Browser Agent        (open_url, search youtube, browse web)
  ├── File Agent           (create/delete/move/copy/rename files & folders, list, search)
  ├── Communication Agent  (send_whatsapp_message)
  └── System Agent         (system_info, cpu, mem, disk, processes, shutdown, terminal)

Central Security Guarantee:
  Sub-agents NEVER bypass the central permission system.
  All tool invocations strictly pass through:
    Tool Registry ➔ Permission Layer ➔ Confirmation Layer ➔ Executor ➔ Audit Log
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.agent.executor import ToolExecutor
from app.agent.planner import ToolCallPlan
from app.agent.tasks import ComplexPlan, PlanStep, TaskManager, TaskState, get_task_manager
from app.agent.tool_registry import AgentToolRegistry
from app.services.event_bus import AgentStatus, get_event_bus
from app.services.groq_client import GroqClient
from app.tools.base import AbstractTool, PermissionLevel

logger = logging.getLogger(__name__)


# ── Specialist Worker Definitions ───────────────────────────────────────────────

class SpecialistRole(str, Enum):
    COMPUTER = "Computer Agent"
    BROWSER = "Browser Agent"
    FILE = "File Agent"
    COMMUNICATION = "Communication Agent"
    SYSTEM = "System Agent"


@dataclass
class SpecialistWorker:
    """Specialized domain worker handling a cohesive subset of computer control tools."""

    name: SpecialistRole
    description: str
    tool_names: list[str]
    icon: str

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in self.tool_names


SPECIALIST_WORKERS: dict[SpecialistRole, SpecialistWorker] = {
    SpecialistRole.COMPUTER: SpecialistWorker(
        name=SpecialistRole.COMPUTER,
        description="Manages Windows desktop applications, processes, screen capture, and workstation locking.",
        tool_names=["open_application", "close_application", "lock_computer", "take_screenshot"],
        icon="monitor",
    ),
    SpecialistRole.BROWSER: SpecialistWorker(
        name=SpecialistRole.BROWSER,
        description="Handles web browser navigation, web searches, YouTube lookups, and URLs.",
        tool_names=["open_url"],
        icon="globe",
    ),
    SpecialistRole.FILE: SpecialistWorker(
        name=SpecialistRole.FILE,
        description="Performs sandboxed filesystem operations: directory and file creation, deletion, copy, move, search.",
        tool_names=[
            "create_folder",
            "delete_folder",
            "create_file",
            "delete_file",
            "move_file",
            "copy_file",
            "rename_file",
            "list_directory",
            "search_files",
            "open_folder",
        ],
        icon="folder",
    ),
    SpecialistRole.COMMUNICATION: SpecialistWorker(
        name=SpecialistRole.COMMUNICATION,
        description="Manages instant messaging and communication channels such as WhatsApp.",
        tool_names=["send_whatsapp_message"],
        icon="message-circle",
    ),
    SpecialistRole.SYSTEM: SpecialistWorker(
        name=SpecialistRole.SYSTEM,
        description="Monitors hardware telemetry, running processes, system power states, time, and controlled shell commands.",
        tool_names=[
            "system_information",
            "cpu_usage",
            "memory_usage",
            "disk_usage",
            "running_processes",
            "shutdown_computer",
            "restart_computer",
            "get_current_time",
            "run_command",
        ],
        icon="cpu",
    ),
}


def resolve_specialist_for_tool(tool_name: str) -> SpecialistWorker:
    """Resolve which specialized worker owns a given tool."""
    for worker in SPECIALIST_WORKERS.values():
        if worker.can_handle(tool_name):
            return worker
    return SPECIALIST_WORKERS[SpecialistRole.SYSTEM]


# ── Supervisor Agent ────────────────────────────────────────────────────────────

class SupervisorAgent:
    """
    Supervisor Agent responsible for:
      1. Analyzing incoming user commands to determine complexity.
      2. Generating a multi-step plan assigning tasks to specialist workers.
      3. For complex workflows: holding execution in WAITING_APPROVAL until the user approves.
      4. For low-risk commands: delegating immediately without approval interruption.
      5. For high-risk commands: enforcing confirmation tickets.
      6. Executing all tools exclusively through the central ToolExecutor.
    """

    def __init__(
        self,
        groq_client: GroqClient,
        registry: AgentToolRegistry,
        executor: ToolExecutor,
    ) -> None:
        self._client = groq_client
        self._registry = registry
        self._executor = executor

    def is_complex_command(self, command: str) -> bool:
        """
        Heuristic and syntactic evaluation of whether a command requires a multi-step workflow.
        Examples of complex commands:
          - "Find a React tutorial on YouTube, open VS Code, and create a folder called ReactPractice"
          - "Open Chrome, create a text file, and take a screenshot"
        """
        cmd_lower = command.lower()
        # Check for multi-clause connectors
        multi_patterns = [
            r"\b(?:and\s+then|then|and\s+also|and|after\s+that)\b",
            r"[,;]\s*(?:open|create|search|find|delete|send|run|check)",
        ]
        # Count distinct action verbs
        action_verbs = ["open", "create", "search", "find", "delete", "make", "play", "send", "lock", "screenshot", "run"]
        verb_count = sum(1 for v in action_verbs if re.search(rf"\b{v}\b", cmd_lower))

        has_connector = any(re.search(p, cmd_lower) for p in multi_patterns)
        return verb_count >= 2 and has_connector

    async def decompose_multi_step_plan(self, command: str) -> ComplexPlan | None:
        """
        Use Groq LLM with structured decomposition instructions to generate a multi-step plan.
        Falls back to rule-based decomposition if LLM parsing encounters issues.
        """
        system_prompt = (
            "You are the NOVA AI Supervisor Agent running on Windows.\n"
            "Analyze the user's multi-step command and decompose it into a sequential plan.\n"
            "Assign each step to exactly one of the 5 specialized workers:\n"
            "  1. 'Browser Agent' (tools: open_url)\n"
            "  2. 'Computer Agent' (tools: open_application, close_application, lock_computer, take_screenshot)\n"
            "  3. 'File Agent' (tools: create_folder, delete_folder, create_file, delete_file, move_file, copy_file, rename_file, list_directory, search_files, open_folder)\n"
            "  4. 'Communication Agent' (tools: send_whatsapp_message)\n"
            "  5. 'System Agent' (tools: system_information, cpu_usage, memory_usage, disk_usage, running_processes, shutdown_computer, restart_computer, get_current_time, run_command)\n\n"
            "Return a strictly valid JSON object with format:\n"
            "{\n"
            '  "summary": "Brief explanation of plan",\n'
            '  "steps": [\n'
            '    {\n'
            '      "index": 1,\n'
            '      "specialist": "Browser Agent",\n'
            '      "action": "Search YouTube for React tutorial",\n'
            '      "tool_name": "open_url",\n'
            '      "arguments": {"url": "https://www.youtube.com/results?search_query=React+tutorial"}\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Do NOT return markdown fences or explanation. Return ONLY JSON."
        )

        try:
            raw_reply = await self._client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": command},
                ],
                temperature=0.1,
            )
            clean_reply = raw_reply.strip()
            if clean_reply.startswith("```"):
                clean_reply = clean_reply.split("```")[1]
                if clean_reply.startswith("json"):
                    clean_reply = clean_reply[4:]
                clean_reply = clean_reply.strip()

            parsed = json.loads(clean_reply)
            steps_data = parsed.get("steps", [])
            plan_steps: list[PlanStep] = []

            for idx, s in enumerate(steps_data):
                specialist_str = s.get("specialist", SpecialistRole.SYSTEM.value)
                tool_name = s.get("tool_name", "")
                # Validate tool exists in registry
                if not self._registry.has_tool(tool_name):
                    # Fallback mapping
                    worker = resolve_specialist_for_tool(tool_name)
                    specialist_str = worker.name.value

                plan_steps.append(
                    PlanStep(
                        index=idx + 1,
                        specialist=specialist_str,
                        action=s.get("action", f"Execute {tool_name}"),
                        tool_name=tool_name,
                        arguments=s.get("arguments", {}),
                        status="PENDING",
                    )
                )

            if plan_steps:
                return ComplexPlan(
                    summary=parsed.get("summary", f"Multi-step execution plan for: {command}"),
                    steps=plan_steps,
                    estimated_operations=len(plan_steps),
                )
        except Exception as exc:
            logger.warning("LLM multi-step decomposition failed: %s. Using rule-based fallback.", exc)

        # ── Rule-Based Fallback Decomposition ──────────────────────────────────
        return self._heuristic_decomposition(command)

    def _heuristic_decomposition(self, command: str) -> ComplexPlan:
        """Reliable rule-based decomposition for common combined commands."""
        steps: list[PlanStep] = []
        cmd_lower = command.lower()
        idx = 1

        # 1. YouTube or Web search
        if "youtube" in cmd_lower:
            query = "React tutorial"
            if "for" in cmd_lower:
                m = re.search(r"(?:find|search|play|for)\s+([^,]+?)(?:\s+on\s+youtube|,|\s+and|\.|$)", cmd_lower)
                if m:
                    query = m.group(1).strip()
            elif "react" in cmd_lower:
                query = "React tutorial"

            steps.append(
                PlanStep(
                    index=idx,
                    specialist=SpecialistRole.BROWSER.value,
                    action=f"Search YouTube for {query}",
                    tool_name="open_url",
                    arguments={"url": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"},
                    status="PENDING",
                )
            )
            idx += 1
        elif "open" in cmd_lower and ("browser" in cmd_lower or "google" in cmd_lower or "chrome" in cmd_lower):
            steps.append(
                PlanStep(
                    index=idx,
                    specialist=SpecialistRole.BROWSER.value,
                    action="Open Web Browser",
                    tool_name="open_url",
                    arguments={"url": "https://www.google.com"},
                    status="PENDING",
                )
            )
            idx += 1

        # 2. VS Code or Application
        if "vs code" in cmd_lower or "vscode" in cmd_lower:
            steps.append(
                PlanStep(
                    index=idx,
                    specialist=SpecialistRole.COMPUTER.value,
                    action="Open VS Code",
                    tool_name="open_application",
                    arguments={"app_name": "VS Code"},
                    status="PENDING",
                )
            )
            idx += 1
        elif "notepad" in cmd_lower:
            steps.append(
                PlanStep(
                    index=idx,
                    specialist=SpecialistRole.COMPUTER.value,
                    action="Open Notepad",
                    tool_name="open_application",
                    arguments={"app_name": "Notepad"},
                    status="PENDING",
                )
            )
            idx += 1

        # 3. Folder creation
        folder_match = re.search(
            r"create\s+(?:a\s+)?folder\s+(?:called\s+|named\s+)?['\"]?([a-zA-Z0-9_\-\s]+)['\"]?",
            command,
            re.IGNORECASE,
        )
        if folder_match:
            folder_name = folder_match.group(1).strip().strip("'\"")
            # If not absolute, anchor to Desktop or home directory so it satisfies allowed_base_paths
            if not os.path.isabs(folder_name):
                desktop = Path.home() / "Desktop"
                target_path = str(desktop / folder_name) if desktop.exists() else str(Path.home() / folder_name)
            else:
                target_path = folder_name

            steps.append(
                PlanStep(
                    index=idx,
                    specialist=SpecialistRole.FILE.value,
                    action=f"Create folder '{folder_name}'",
                    tool_name="create_folder",
                    arguments={"folder_path": target_path},
                    status="PENDING",
                )
            )
            idx += 1

        # Fallback if no steps extracted
        if not steps:
            steps.append(
                PlanStep(
                    index=1,
                    specialist=SpecialistRole.SYSTEM.value,
                    action="Execute system task",
                    tool_name="get_current_time",
                    arguments={},
                    status="PENDING",
                )
            )

        return ComplexPlan(
            summary=f"Coordinated execution across {len(steps)} specialist agents",
            steps=steps,
            estimated_operations=len(steps),
        )

    # ── Approved Plan Execution ────────────────────────────────────────────────

    async def execute_approved_plan(self, task_id: str) -> dict[str, Any]:
        """
        Execute an approved multi-step plan through the central ToolExecutor.
        Each tool execution strictly passes through PermissionChecker and AuditLogger.
        """
        start_time = time.time()
        task_mgr = get_task_manager()
        task = task_mgr.get_task(task_id)
        if not task or not task.plan:
            return {"success": False, "error": f"Task {task_id} has no plan to execute."}

        task_mgr.approve_task(task_id)
        bus = get_event_bus()
        bus.set_status(AgentStatus.EXECUTING, f"Executing multi-step plan ({len(task.plan.steps)} operations)...")
        bus.publish_event(
            "agent.started",
            {
                "request_id": task_id,
                "command": task.description,
                "task_id": task_id,
                "is_complex": True,
            },
        )

        executed_results = []
        all_success = True

        for idx, step in enumerate(task.plan.steps):
            if task_mgr.is_cancelled(task_id):
                step.status = "CANCELLED"
                task_mgr.update_plan_step(task_id, idx, "CANCELLED")
                break

            step.status = "RUNNING"
            task_mgr.update_plan_step(task_id, idx, "RUNNING")
            task_mgr.update_step(task_id, idx, "active")

            # Resolve specialist worker
            worker = resolve_specialist_for_tool(step.tool_name)
            logger.info("Step %d assigned to specialist %s -> tool %s", idx + 1, worker.name.value, step.tool_name)

            tool_plan = ToolCallPlan(
                tool_name=step.tool_name,
                tool_call_id=f"step_{idx+1}",
                arguments=step.arguments,
            )

            # Central ToolExecutor execution
            records = await self._executor.execute_plan(
                [tool_plan],
                command=task.description,
                confirmed=True,  # Plan was pre-approved by user
                request_id=task_id,
                task_id=task_id,
            )

            record = records[0] if records else None
            success = record.result.success if record else False
            out_text = record.result.output if (record and record.result.success) else (record.result.error if record else "Execution failed")

            if not success:
                all_success = False

            step_duration = record.result.output and 0.5 or 0.2
            step.status = "COMPLETED" if success else "FAILED"
            step.output = out_text
            step.error = None if success else out_text

            task_mgr.update_plan_step(task_id, idx, step.status, duration=step_duration, output=out_text)
            task_mgr.update_step(task_id, idx, "completed" if success else "failed")

            executed_results.append({
                "step": idx + 1,
                "specialist": worker.name.value,
                "action": step.action,
                "success": success,
                "output": out_text,
            })

        # Summary response
        final_response = f"Completed {len(executed_results)} plan operations:\n" + "\n".join(
            f"  {r['step']}. [{r['specialist']}] {r['action']} — {'✓ Success' if r['success'] else '✗ Failed'}"
            for r in executed_results
        )

        task_mgr.complete_task(
            task_id,
            final_response,
            error=None if all_success else "One or more steps encountered errors.",
        )
        bus.set_status(AgentStatus.ONLINE, "Ready")
        duration = round(time.time() - start_time, 2)
        bus.publish_event(
            "agent.completed",
            {
                "request_id": task_id,
                "response": final_response,
                "success": all_success,
                "duration": duration,
                "tool_calls": executed_results,
                "task_id": task_id,
            },
        )

        return {
            "success": all_success,
            "task_id": task_id,
            "response": final_response,
            "steps": executed_results,
        }
