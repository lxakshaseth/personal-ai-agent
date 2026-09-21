"""
Task lifecycle manager for NOVA AI agent.
Tracks active, paused, completed, and cancelled tasks with safe asyncio cancellation,
disk persistence, plan approval, and 8 formal task states.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatusStr(str):
    """Case-insensitive string representation of TaskState for backwards-compatibility."""

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (str, Enum)):
            val = other.value if isinstance(other, Enum) else str(other)
            return self.upper() == val.upper()
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.upper())


class TaskStep(BaseModel):
    name: str
    icon: str = "brain"  # brain, browser, wrench, check, terminal, message-square, folder
    status: str = "pending"  # pending, active, completed, failed, cancelled


class PlanStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    index: int = 1
    specialist: str  # "Browser Agent", "Computer Agent", "File Agent", "Communication Agent", "System Agent"
    action: str      # e.g. "Search YouTube for React tutorial"
    tool_name: str   # e.g. "open_url"
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    duration_seconds: float | None = None
    output: str | None = None
    error: str | None = None


class ComplexPlan(BaseModel):
    summary: str
    steps: list[PlanStep] = Field(default_factory=list)
    estimated_operations: int = 0


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    status: str = TaskState.CREATED.value
    is_complex: bool = False
    plan: ComplexPlan | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    duration_seconds: float = 0.0
    result: str | None = None
    error: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not isinstance(self.status, TaskStatusStr):
            self.status = TaskStatusStr(self.status)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "status" and isinstance(value, str) and not isinstance(value, TaskStatusStr):
            value = TaskStatusStr(value)
        super().__setattr__(name, value)


class TaskManager:
    """Manages task lifecycle with pause, resume, plan approval, and persistence."""

    def __init__(self, persistence_file: str = "logs/tasks_store.json", max_history: int = 100) -> None:
        self._tasks: dict[str, AgentTask] = {}
        self._active_task_id: str | None = None
        self._cancelled_tasks: set[str] = set()
        self._paused_tasks: set[str] = set()
        self._running_handles: dict[str, asyncio.Task[Any]] = {}
        self._persistence_file = Path(persistence_file)
        self._max_history = max_history

        # Load persisted tasks from disk on initialize
        self._load_from_disk()

    # ── Disk Persistence ───────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        if not self._persistence_file.exists():
            return
        try:
            with self._persistence_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        try:
                            task = AgentTask(**item)
                            task.status = TaskStatusStr(task.status)
                            self._tasks[task.id] = task
                        except Exception as parse_err:
                            logger.warning("Skipping corrupted task record: %s", parse_err)
            logger.info("Loaded %d persisted tasks from %s", len(self._tasks), self._persistence_file)
        except Exception as exc:
            logger.warning("Could not load persisted tasks from %s: %s", self._persistence_file, exc)

    def _save_to_disk(self) -> None:
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            tasks_list = [t.model_dump() for t in self.list_tasks()[:self._max_history]]
            temp_path = self._persistence_file.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(tasks_list, f, indent=2)
            temp_path.replace(self._persistence_file)
        except Exception as exc:
            logger.warning("Could not persist tasks to %s: %s", self._persistence_file, exc)

    # ── Task Lifecycle ─────────────────────────────────────────────────────────

    def register_task_handle(self, task_id: str, handle: asyncio.Task[Any]) -> None:
        """Register an asyncio Task handle for cancellation."""
        self._running_handles[task_id] = handle

    def unregister_task_handle(self, task_id: str) -> None:
        """Unregister an asyncio Task handle when execution finishes."""
        self._running_handles.pop(task_id, None)

    def create_task(self, description: str) -> AgentTask:
        task_id = str(uuid.uuid4())
        initial_steps = [
            TaskStep(name="Planning", icon="brain", status="active"),
            TaskStep(name="Execution", icon="wrench", status="pending"),
            TaskStep(name="Completed", icon="check", status="pending"),
        ]
        task = AgentTask(
            id=task_id,
            description=description,
            status=TaskState.PLANNING.value,
            steps=initial_steps,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._tasks[task_id] = task
        self._active_task_id = task_id

        self._save_to_disk()
        get_event_bus().publish_event("task_created", task.model_dump())
        return task

    def set_plan(self, task_id: str, plan: ComplexPlan) -> None:
        """Attach a multi-step plan to the task and transition to WAITING_APPROVAL."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.plan = plan
        task.is_complex = True
        task.status = TaskState.WAITING_APPROVAL.value
        task.updated_at = time.time()

        # Update UI pipeline steps to match plan
        task.steps = [
            TaskStep(
                name=f"{step.specialist}: {step.action}",
                icon="browser" if "Browser" in step.specialist else "folder" if "File" in step.specialist else "wrench",
                status="pending",
            )
            for step in plan.steps
        ]
        if not task.steps:
            task.steps = [
                TaskStep(name="Planning", icon="brain", status="completed"),
                TaskStep(name="Approval Required", icon="wrench", status="active"),
                TaskStep(name="Completed", icon="check", status="pending"),
            ]

        self._save_to_disk()
        get_event_bus().publish_event("task_updated", task.model_dump())
        get_event_bus().publish_event(
            "plan_generated",
            {
                "task_id": task_id,
                "plan": plan.model_dump(),
                "status": TaskState.WAITING_APPROVAL.value,
            },
        )

    def approve_task(self, task_id: str) -> bool:
        """Transition task from WAITING_APPROVAL to RUNNING."""
        task = self._tasks.get(task_id)
        if not task or task.status != TaskState.WAITING_APPROVAL.value:
            return False

        task.status = TaskState.RUNNING.value
        task.updated_at = time.time()
        self._save_to_disk()
        get_event_bus().publish_event("task_updated", task.model_dump())
        get_event_bus().publish_event("task_approved", {"task_id": task_id})
        return True

    def get_active_task(self) -> AgentTask | None:
        active_states = (
            TaskState.PLANNING.value,
            TaskState.WAITING_APPROVAL.value,
            TaskState.RUNNING.value,
            TaskState.PAUSED.value,
            "planning",
            "executing",
            "paused",
        )
        if self._active_task_id and self._active_task_id in self._tasks:
            task = self._tasks[self._active_task_id]
            if task.status in active_states and not self.is_cancelled(task.id):
                return task

        return None

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, state_filter: str | None = None) -> list[AgentTask]:
        tasks = list(self._tasks.values())
        if state_filter and state_filter.upper() != "ALL":
            filter_val = state_filter.upper()
            tasks = [t for t in tasks if t.status.upper() == filter_val or t.status.lower() == state_filter.lower()]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def update_step(
        self,
        task_id: str,
        step_index: int,
        status: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return

        if 0 <= step_index < len(task.steps):
            task.steps[step_index].status = status
            if name:
                task.steps[step_index].name = name
            if icon:
                task.steps[step_index].icon = icon

        task.updated_at = time.time()
        self._save_to_disk()
        get_event_bus().publish_event("task_updated", task.model_dump())

    def update_plan_step(
        self,
        task_id: str,
        step_index: int,
        status: str,
        duration: float | None = None,
        output: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update the status and execution metrics of a specific plan step."""
        task = self._tasks.get(task_id)
        if not task or not task.plan or step_index >= len(task.plan.steps):
            return

        step = task.plan.steps[step_index]
        step.status = status.upper()
        if duration is not None:
            step.duration_seconds = duration
        if output is not None:
            step.output = output
        if error is not None:
            step.error = error

        task.updated_at = time.time()
        self._save_to_disk()
        get_event_bus().publish_event("task_updated", task.model_dump())

    def pause_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status not in (TaskState.PLANNING.value, TaskState.RUNNING.value, "planning", "executing"):
            return False

        task.status = TaskState.PAUSED.value
        task.updated_at = time.time()
        self._paused_tasks.add(task_id)
        self._save_to_disk()
        get_event_bus().publish_event("task_paused", task.model_dump())
        return True

    def resume_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status not in (TaskState.PAUSED.value, "paused"):
            return False

        task.status = TaskState.RUNNING.value
        task.updated_at = time.time()
        self._paused_tasks.discard(task_id)
        self._save_to_disk()
        get_event_bus().publish_event("task_resumed", task.model_dump())
        return True

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status in (TaskState.COMPLETED.value, TaskState.CANCELLED.value, "completed", "cancelled"):
            return False

        task.status = TaskState.CANCELLED.value
        task.updated_at = time.time()
        task.duration_seconds = round(task.updated_at - task.created_at, 1)
        self._cancelled_tasks.add(task_id)

        # Cancel underlying asyncio Task if running
        handle = self._running_handles.get(task_id)
        if handle and not handle.done():
            logger.info("Cancelling asyncio task handle for task %s", task_id)
            handle.cancel()

        if self._active_task_id == task_id:
            self._active_task_id = None

        self._save_to_disk()
        get_event_bus().publish_event("task_cancelled", task.model_dump())
        get_event_bus().publish_event(
            "agent.error",
            {
                "request_id": task_id,
                "error": "Task cancelled by user.",
            },
        )
        return True

    def cancel_active_task(self) -> bool:
        active = self.get_active_task()
        if active:
            return self.cancel_task(active.id)
        return False

    def complete_task(self, task_id: str, result: str, error: str | None = None) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = TaskState.COMPLETED.value if not error else TaskState.FAILED.value
        task.result = result
        task.error = error
        task.updated_at = time.time()
        task.duration_seconds = round(task.updated_at - task.created_at, 1)

        # Mark all steps completed or failed
        for s in task.steps:
            if s.status in ("active", "pending"):
                s.status = "completed" if not error else "failed"

        if task.plan:
            for ps in task.plan.steps:
                if ps.status in ("PENDING", "RUNNING"):
                    ps.status = "COMPLETED" if not error else "FAILED"

        if self._active_task_id == task_id:
            self._active_task_id = None

        self._running_handles.pop(task_id, None)
        self._save_to_disk()
        get_event_bus().publish_event("task_completed", task.model_dump())

    def is_cancelled(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskState.CANCELLED.value, "cancelled"):
            return True
        return task_id in self._cancelled_tasks

    def is_paused(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (TaskState.PAUSED.value, "paused"):
            return True
        return task_id in self._paused_tasks


# ── Global Singleton ─────────────────────────────────────────────────────────

_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
