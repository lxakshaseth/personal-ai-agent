"""
Tool executor — runs planned tool calls with validation, permission checks,
Pydantic argument validation, audit logging, real-time WebSocket event emission,
and cancellation checks.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.agent.planner import ToolCallPlan
from app.agent.tasks import get_task_manager
from app.agent.tool_registry import AgentToolRegistry
from app.security.audit import AuditLogger
from app.security.confirmation_manager import get_confirmation_manager
from app.security.permissions import PermissionChecker
from app.services.event_bus import get_event_bus
from app.tools.base import ToolResult
from app.utils.exceptions import (
    ConfirmationRequiredError,
    PermissionDeniedError,
    ToolNotFoundError,
    ToolValidationError,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Result of executing a single tool call."""

    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: ToolResult
    error: str | None = None


class ToolExecutor:
    """
    Executes tool call plans returned by the planner.

    Injected dependencies:
        registry           – AgentToolRegistry
        permission_checker – PermissionChecker
        audit_logger       – AuditLogger
    """

    def __init__(
        self,
        registry: AgentToolRegistry,
        permission_checker: PermissionChecker,
        audit_logger: AuditLogger,
    ) -> None:
        self._registry = registry
        self._permission_checker = permission_checker
        self._audit_logger = audit_logger

    # ── Public API ─────────────────────────────────────────────────────────────

    async def execute_plan(
        self,
        plans: list[ToolCallPlan],
        *,
        command: str,
        confirmed: bool = False,
        request_id: str | None = None,
        task_id: str | None = None,
    ) -> list[ExecutionRecord]:
        """
        Execute a list of tool call plans sequentially.

        Args:
            plans:      Tool call plans from the planner.
            command:    Original user command (written to audit log).
            confirmed:  Whether the user pre-confirmed HIGH-risk actions.
            request_id: Unique request correlation ID for events.
            task_id:    Associated AgentTask ID to check for cancellation.

        Returns:
            List of ExecutionRecord, one per plan item.
        """
        records: list[ExecutionRecord] = []
        task_mgr = get_task_manager()

        for idx, plan in enumerate(plans):
            if task_id and task_mgr.is_cancelled(task_id):
                logger.info("Halting execution of plans: task %s was cancelled.", task_id)
                break

            record = await self._execute_one(
                plan,
                command=command,
                confirmed=confirmed,
                request_id=request_id or task_id or "",
                task_id=task_id,
            )
            records.append(record)
            if not record.result.success:
                logger.warning("Tool %r failed: %s", plan.tool_name, record.result.error)

        return records

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _execute_one(
        self,
        plan: ToolCallPlan,
        *,
        command: str,
        confirmed: bool = False,
        request_id: str = "",
        task_id: str | None = None,
    ) -> ExecutionRecord:
        bus = get_event_bus()
        error_msg: str | None = None
        result = ToolResult(success=False, output="", error="Unknown error")
        start_time = time.time()

        # Emit tool.started
        bus.publish_event(
            "tool.started",
            {
                "request_id": request_id,
                "tool": plan.tool_name,
                "arguments": plan.arguments,
            },
        )

        try:
            # 1. Tool lookup
            tool = self._registry.get_tool(plan.tool_name)

            # 2. Pydantic argument validation (if tool declares an input model)
            validated_args = self._validate_args(tool, plan.arguments)

            # 3. Permission check
            self._permission_checker.check(tool, validated_args, confirmed=confirmed)

            # Emit tool.progress
            bus.publish_event(
                "tool.progress",
                {
                    "request_id": request_id,
                    "tool": plan.tool_name,
                    "progress": 0.5,
                    "elapsed": round(time.time() - start_time, 2),
                    "message": f"Executing {plan.tool_name}...",
                },
            )

            # Check for cancellation right before running tool
            if task_id and get_task_manager().is_cancelled(task_id):
                error_msg = "Task cancelled by user."
                result = ToolResult(success=False, output="", error=error_msg)
            else:
                # 4. Execute
                result = await tool.execute(**validated_args)
                logger.info("Tool %r executed — success=%s", plan.tool_name, result.success)

        except ToolNotFoundError as exc:
            error_msg = str(exc)
            result = ToolResult(success=False, output="", error=error_msg)
            logger.error("Unknown tool requested: %r", plan.tool_name)

        except ToolValidationError as exc:
            error_msg = str(exc)
            result = ToolResult(success=False, output="", error=error_msg)
            logger.warning("Argument validation failed for %r: %s", plan.tool_name, error_msg)

        except PermissionDeniedError as exc:
            error_msg = str(exc)
            result = ToolResult(success=False, output="", error=error_msg)
            logger.warning("Permission denied for %r: %s", plan.tool_name, error_msg)

        except ConfirmationRequiredError as exc:
            error_msg = str(exc)
            result = ToolResult(success=False, output="", error=error_msg)
            logger.info("Confirmation required for %r", plan.tool_name)
            ticket_id = None
            try:
                ticket = get_confirmation_manager().create_ticket(
                    tool_name=plan.tool_name,
                    arguments=plan.arguments,
                    command=command,
                    reason=error_msg,
                )
                ticket_id = ticket.ticket_id
            except Exception as e:
                logger.warning("Could not create confirmation ticket: %s", e)

            # Emit confirmation.required
            bus.publish_event(
                "confirmation.required",
                {
                    "request_id": request_id,
                    "tool": plan.tool_name,
                    "ticket_id": ticket_id,
                    "arguments": plan.arguments,
                    "reason": error_msg,
                },
            )

        except Exception as exc:
            error_msg = f"Unexpected error in tool {plan.tool_name!r}: {exc}"
            result = ToolResult(success=False, output="", error=error_msg)
            logger.exception("Tool %r raised an unexpected exception", plan.tool_name)

        finally:
            duration = round(time.time() - start_time, 2)
            # Emit tool.completed
            bus.publish_event(
                "tool.completed",
                {
                    "request_id": request_id,
                    "tool": plan.tool_name,
                    "success": result.success,
                    "duration": duration,
                    "output": result.output,
                    "error": result.error if not result.success else None,
                },
            )

            self._audit_logger.log(
                command=command,
                tool_name=plan.tool_name,
                tool_args=plan.arguments,
                success=result.success,
                output=result.output,
                error=result.error,
                permission_level=getattr(
                    self._registry.get(plan.tool_name), "permission_level", None
                ) and self._registry.get(plan.tool_name).permission_level.value,
            )

        return ExecutionRecord(
            tool_name=plan.tool_name,
            tool_call_id=plan.tool_call_id,
            arguments=plan.arguments,
            result=result,
            error=error_msg,
        )

    def _validate_args(
        self, tool: Any, raw_args: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Validate *raw_args* against the tool's Pydantic input model if one exists.
        """
        input_model = getattr(tool, "input_model", None)
        if input_model is None:
            return raw_args

        try:
            validated = input_model(**raw_args)
            return validated.model_dump()
        except ValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            raise ToolValidationError(
                f"Invalid arguments for tool {tool.name!r}: {errors}",
                tool_name=tool.name,
            ) from exc
