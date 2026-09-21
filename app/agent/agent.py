"""
PersonalAgent — the concrete agent implementation.

Full execution flow:
  User command
      ↓
  GroqPlanner.plan()        — LLM decides which tool(s) to call
      ↓
  ToolExecutor.execute_plan() — validate args, check permissions, run tool
      ↓
  GroqPlanner.synthesize_response() — LLM writes a friendly reply
      ↓
  AgentOutput returned to the API layer
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.agent.base import AbstractAgent, AgentInput, AgentOutput
from app.agent.executor import ToolExecutor
from app.agent.history import CommandHistoryRecord, get_command_history_store
from app.agent.fast_router import FastRouter, ResponseMode
from app.agent.planner import GroqPlanner, ToolCallPlan
from app.agent.schemas import GroqErrorType
from app.agent.supervisor import SupervisorAgent
from app.agent.tasks import get_task_manager
from app.config.settings import get_settings
from app.services.event_bus import AgentStatus, EventType, get_event_bus
from app.utils.exceptions import PlannerError

logger = logging.getLogger(__name__)


class PersonalAgent(AbstractAgent):
    """
    Production AI agent that:
    - Plans actions using Groq LLM function-calling.
    - Executes registered tools (never arbitrary code).
    - Coordinates multi-step plans across specialist workers via SupervisorAgent.
    - Returns a natural-language response synthesised by the LLM.
    """

    def __init__(
        self,
        planner: GroqPlanner,
        executor: ToolExecutor,
        supervisor: SupervisorAgent | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._settings = get_settings()
        self._supervisor = supervisor or SupervisorAgent(
            groq_client=planner._client,
            registry=planner._registry,
            executor=executor,
        )

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """
        End-to-end command execution.

        Handles all error paths with user-friendly messages.
        """
        command = agent_input.command.strip()
        command_id = str(uuid.uuid4())
        start_time = time.time()
        bus = get_event_bus()

        logger.info(
            "Agent.run command=%r session=%s confirmed=%s",
            command,
            agent_input.session_id,
            agent_input.confirmed,
        )

        if not command:
            return AgentOutput(
                success=False,
                response="I didn't receive a command. Please tell me what you'd like me to do.",
                error="Empty command",
            )

        task_mgr = get_task_manager()
        task = task_mgr.create_task(command)

        curr_async_task = None
        try:
            curr_async_task = asyncio.current_task()
        except RuntimeError:
            pass
        if curr_async_task:
            task_mgr.register_task_handle(task.id, curr_async_task)

        bus.set_status(AgentStatus.THINKING, "Understanding command...")
        bus.publish_event(
            "agent.started",
            {
                "request_id": command_id,
                "command": command,
                "session_id": agent_input.session_id,
                "task_id": task.id,
            },
        )
        bus.publish_event(
            "agent.thinking",
            {
                "request_id": command_id,
                "command": command,
                "task_id": task.id,
            },
        )
        bus.publish(
            EventType.COMMAND_STARTED,
            {"id": command_id, "command": command, "session_id": agent_input.session_id, "task_id": task.id},
        )

        try:
            # ── 0. Fast Path Deterministic Router (0ms LLM latency) ────────────────
            fast_route = FastRouter.match(command)
            if fast_route.matched:
                if fast_route.mode == ResponseMode.CHAT:
                    duration = round(time.time() - start_time, 2)
                    reply = fast_route.direct_response or "Hey! What can I help you with?"
                    task_mgr.complete_task(task.id, reply)
                    bus.set_status(AgentStatus.ONLINE, "Ready", request_id=command_id)
                    bus.publish_event(
                        "agent.completed",
                        {
                            "request_id": command_id,
                            "response": reply,
                            "success": True,
                            "duration": duration,
                            "tool_calls": [],
                            "task_id": task.id,
                        },
                    )
                    out = AgentOutput(
                        success=True,
                        response=reply,
                        tool_calls=[],
                        should_speak=True,
                        mode="CHAT",
                    )
                    self._record_history(command_id, command, out, start_time)
                    if self._settings.debug_performance:
                        logger.info("[ROUTER] Fast CHAT response returned in %0.1fms", duration * 1000)
                    return out

                elif fast_route.tool_name:
                    bus.publish_event(
                        "tool.selected",
                        {
                            "request_id": command_id,
                            "tool": fast_route.tool_name,
                            "arguments": fast_route.arguments,
                            "task_id": task.id,
                        },
                    )
                    bus.set_status(AgentStatus.EXECUTING, f"Executing {fast_route.tool_name}...", request_id=command_id)
                    tool_plan = ToolCallPlan(
                        tool_name=fast_route.tool_name,
                        tool_call_id=f"fast_{uuid.uuid4().hex[:6]}",
                        arguments=fast_route.arguments,
                    )
                    records = await self._executor.execute_plan(
                        [tool_plan],
                        command=command,
                        confirmed=agent_input.confirmed,
                        request_id=command_id,
                        task_id=task.id,
                    )
                    rec = records[0] if records else None
                    success = rec.result.success if rec else False
                    tool_output = rec.result.output if (rec and rec.result.success) else (rec.result.error if rec else "Execution failed")

                    if success:
                        reply = fast_route.conversational_prefix or tool_output or "Done."
                    else:
                        reply = tool_output or "The operation failed."

                    duration = round(time.time() - start_time, 2)
                    task_mgr.complete_task(task.id, reply, error=None if success else tool_output)
                    bus.set_status(AgentStatus.ONLINE, "Ready", request_id=command_id)
                    tool_dicts = [
                        {
                            "tool": fast_route.tool_name,
                            "args": fast_route.arguments,
                            "success": success,
                            "output": tool_output,
                            "error": None if success else tool_output,
                        }
                    ]
                    bus.publish_event(
                        "agent.completed",
                        {
                            "request_id": command_id,
                            "response": reply,
                            "success": success,
                            "duration": duration,
                            "tool_calls": tool_dicts,
                            "task_id": task.id,
                        },
                    )
                    out = AgentOutput(
                        success=success,
                        response=reply,
                        tool_calls=tool_dicts,
                        should_speak=True,
                        mode="COMMAND",
                    )
                    self._record_history(command_id, command, out, start_time)
                    if self._settings.debug_performance:
                        logger.info("[ROUTER] Fast tool %s executed in %0.1fms", fast_route.tool_name, duration * 1000)
                    return out

            # ── 0b. Knowledge Query Fast Path (bypass tool-calling overhead) ────────
            # Pure Q&A/explanation queries go directly to streaming LLM, skipping
            # the 25-tool prompt that causes 8s+ timeouts on complex answers.
            from app.agent.fast_router import is_knowledge_query
            if is_knowledge_query(command):
                bus.set_status(AgentStatus.THINKING, "Streaming knowledge response...")
                from app.services.groq_client import get_groq_client
                groq = get_groq_client()
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are NOVA, a helpful Windows AI assistant. "
                            "Answer concisely and clearly. For voice responses keep answers under 3 sentences "
                            "unless the user explicitly asks for more detail."
                        ),
                    },
                    {"role": "user", "content": command},
                ]
                try:
                    tokens = []
                    async for tok in groq.stream_chat_completion(messages):
                        tokens.append(tok)
                    reply = "".join(tokens).strip() or "I'm not sure about that."
                except Exception as exc:
                    logger.warning("Knowledge stream failed, falling through to planner: %s", exc)
                    reply = None

                if reply:
                    duration = round(time.time() - start_time, 2)
                    task_mgr.complete_task(task.id, reply)
                    bus.set_status(AgentStatus.ONLINE, "Ready", request_id=command_id)
                    bus.publish_event(
                        "agent.completed",
                        {
                            "request_id": command_id,
                            "response": reply,
                            "success": True,
                            "duration": duration,
                            "tool_calls": [],
                            "task_id": task.id,
                        },
                    )
                    out = AgentOutput(
                        success=True,
                        response=reply,
                        tool_calls=[],
                        should_speak=True,
                        mode="CHAT",
                    )
                    self._record_history(command_id, command, out, start_time)
                    logger.info("[KNOWLEDGE] Streamed response in %0.1fms (no tool overhead)", duration * 1000)
                    return out

            # ── 1. Complex Multi-Step Task Check (Supervisor Agent) ─────────────────
            if self._supervisor.is_complex_command(command) and not agent_input.confirmed:
                task_mgr.update_step(task.id, 0, "active", "Supervisor Decomposition", "brain")
                bus.publish_event(
                    "agent.planning",
                    {
                        "request_id": command_id,
                        "command": command,
                        "task_id": task.id,
                        "is_complex": True,
                    },
                )
                plan = await self._supervisor.decompose_multi_step_plan(command)
                if plan and plan.steps:
                    task_mgr.set_plan(task.id, plan)
                    bus.set_status(
                        AgentStatus.WAITING_CONFIRMATION,
                        f"Plan ready: {plan.estimated_operations} operations awaiting approval",
                    )
                    step_lines = "\n".join(f"  {s.index}. {s.specialist} → {s.action}" for s in plan.steps)
                    plan_msg = (
                        f"I have created a multi-step execution plan for this task:\n\n"
                        f"{step_lines}\n\n"
                        f"Estimated operations: {plan.estimated_operations}\n\n"
                        f"Please review the plan card and click Execute to start."
                    )
                    duration = round(time.time() - start_time, 2)
                    bus.publish_event(
                        "agent.completed",
                        {
                            "request_id": command_id,
                            "response": plan_msg,
                            "success": True,
                            "duration": duration,
                            "tool_calls": [],
                            "task_id": task.id,
                            "is_complex": True,
                            "waiting_approval": True,
                            "plan": plan.model_dump(),
                        },
                    )
                    out = AgentOutput(
                        success=True,
                        response=plan_msg,
                        tool_calls=[],
                        metadata={
                            "task_id": task.id,
                            "is_complex": True,
                            "waiting_approval": True,
                            "plan": plan.model_dump(),
                        },
                    )
                    self._record_history(command_id, command, out, start_time)
                    return out

            # ── 1. Plan ────────────────────────────────────────────────────────────
            task_mgr.update_step(task.id, 0, "active", "Planning", "brain")
            bus.publish_event(
                "agent.planning",
                {
                    "request_id": command_id,
                    "command": command,
                    "task_id": task.id,
                },
            )
            plan_result = await self._planner.plan(command)
        except asyncio.CancelledError:
            logger.info("Agent planning cancelled for task %s", task.id)
            bus.set_status(AgentStatus.ONLINE, "Ready")
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": "Task cancelled by user.", "task_id": task.id},
            )
            task_mgr.cancel_task(task.id)
            return AgentOutput(success=False, response="Task was cancelled by user.", error="Cancelled")
        except PlannerError as exc:
            bus.set_status(AgentStatus.ERROR, f"Planning failed: {exc.message}")
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": exc.message, "task_id": task.id},
            )
            out = self._handle_planner_error(exc, command)
            task_mgr.complete_task(task.id, out.response, error=exc.message)
            self._record_history(command_id, command, out, start_time)
            return out
        except Exception as exc:
            logger.exception("Unexpected planner failure for command %r", command)
            bus.set_status(AgentStatus.ERROR, str(exc))
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": str(exc), "task_id": task.id},
            )
            out = AgentOutput(
                success=False,
                response="Something unexpected went wrong. Please try again.",
                error=str(exc),
            )
            task_mgr.complete_task(task.id, out.response, error=str(exc))
            self._record_history(command_id, command, out, start_time)
            return out
        finally:
            task_mgr.unregister_task_handle(task.id)

        if task_mgr.is_cancelled(task.id):
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": "Task cancelled by user.", "task_id": task.id},
            )
            return AgentOutput(success=False, response="Task was cancelled by user.", error="Cancelled")

        # ── 2. No tool calls — plain LLM answer ───────────────────────────────
        if not plan_result.has_tool_calls:
            task_mgr.update_step(task.id, 0, "completed")
            task_mgr.update_step(task.id, 1, "completed", "Answer", "check")
            task_mgr.complete_task(task.id, plan_result.text_reply or "Done.")
            bus.set_status(AgentStatus.ONLINE, "Ready")
            duration = round(time.time() - start_time, 2)
            bus.publish_event(
                "agent.completed",
                {
                    "request_id": command_id,
                    "response": plan_result.text_reply or "Done.",
                    "success": True,
                    "duration": duration,
                    "tool_calls": [],
                    "task_id": task.id,
                },
            )
            out = AgentOutput(
                success=True,
                response=plan_result.text_reply or "Done.",
                tool_calls=[],
            )
            self._record_history(command_id, command, out, start_time)
            return out

        # ── 3. Execute tools ───────────────────────────────────────────────────
        task_mgr.update_step(task.id, 0, "completed")
        tool_names = ", ".join(t.tool_name for t in plan_result.tool_calls)

        # Emit tool.selected for each chosen tool
        for t_plan in plan_result.tool_calls:
            bus.publish_event(
                "tool.selected",
                {
                    "request_id": command_id,
                    "tool": t_plan.tool_name,
                    "arguments": t_plan.arguments,
                    "task_id": task.id,
                },
            )

        # Determine primary domain category for UI pipeline step
        if any("url" in t.tool_name or "browser" in t.tool_name or "youtube" in command.lower() for t in plan_result.tool_calls):
            cat_name, cat_icon = "Browser", "browser"
        elif any("whatsapp" in t.tool_name for t in plan_result.tool_calls):
            cat_name, cat_icon = "WhatsApp", "message-square"
        elif any("folder" in t.tool_name or "file" in t.tool_name for t in plan_result.tool_calls):
            cat_name, cat_icon = "Filesystem", "folder"
        elif any("command" in t.tool_name for t in plan_result.tool_calls):
            cat_name, cat_icon = "Terminal", "terminal"
        else:
            cat_name, cat_icon = plan_result.tool_calls[0].tool_name, "wrench"

        task_mgr.update_step(task.id, 1, "active", cat_name, cat_icon)
        bus.set_status(AgentStatus.EXECUTING, f"Executing {tool_names}...")

        if curr_async_task:
            task_mgr.register_task_handle(task.id, curr_async_task)

        try:
            records = await self._executor.execute_plan(
                plan_result.tool_calls,
                command=command,
                confirmed=agent_input.confirmed,
                request_id=command_id,
                task_id=task.id,
            )
        except asyncio.CancelledError:
            logger.info("Tool execution cancelled for task %s", task.id)
            bus.set_status(AgentStatus.ONLINE, "Ready")
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": "Task cancelled by user.", "task_id": task.id},
            )
            task_mgr.cancel_task(task.id)
            return AgentOutput(success=False, response="Task was cancelled by user.", error="Cancelled")
        finally:
            task_mgr.unregister_task_handle(task.id)

        if task_mgr.is_cancelled(task.id):
            bus.publish_event(
                "agent.error",
                {"request_id": command_id, "error": "Task cancelled by user.", "task_id": task.id},
            )
            return AgentOutput(success=False, response="Task was cancelled by user.", error="Cancelled")

        # ── 4. Build structured result list ───────────────────────────────────
        tool_call_dicts: list[dict] = []
        all_success = True
        waiting_confirmation = False

        for rec in records:
            tool_call_dicts.append({
                "tool": rec.tool_name,
                "args": rec.arguments,
                "success": rec.result.success,
                "output": rec.result.output,
                "error": rec.result.error,
            })
            if not rec.result.success:
                all_success = False
                if rec.result.error and "confirmation" in rec.result.error.lower():
                    waiting_confirmation = True

        # ── 5. Natural-language response ───────────────────────────────────────
        # FAST PATH: single tool succeeded → return its output directly (no LLM call).
        # This eliminates ~1-3s of latency for simple commands like "open YouTube".
        if all_success and len(records) == 1:
            response = records[0].result.output or "Done."
        elif not all_success and len(records) == 1:
            # Single tool failed → return error directly, also no LLM overhead
            response = records[0].result.error or "The operation failed."
        else:
            # Multi-tool or mixed results → LLM synthesises a coherent summary
            try:
                response = await self._planner.synthesize_response(command, tool_call_dicts)
            except Exception:
                parts = []
                for rec in records:
                    mark = "✓" if rec.result.success else "✗"
                    parts.append(f"{mark} {rec.tool_name}: {rec.result.output or rec.result.error}")
                response = "\n".join(parts)

        task_mgr.update_step(task.id, 1, "completed" if all_success else "failed")
        task_mgr.update_step(task.id, 2, "completed" if all_success else "failed", "Completed", "check")
        task_mgr.complete_task(task.id, response, error=None if all_success else "Errors during tool execution")

        if waiting_confirmation:
            bus.set_status(AgentStatus.WAITING_CONFIRMATION, "Waiting for confirmation")
        elif all_success:
            bus.set_status(AgentStatus.ONLINE, "Ready")
        else:
            bus.set_status(AgentStatus.ERROR, "Tool execution completed with warnings/errors")

        duration = round(time.time() - start_time, 2)
        bus.publish_event(
            "agent.completed",
            {
                "request_id": command_id,
                "response": response,
                "success": all_success,
                "duration": duration,
                "tool_calls": tool_call_dicts,
                "task_id": task.id,
            },
        )

        out = AgentOutput(
            success=all_success,
            response=response,
            tool_calls=tool_call_dicts,
            should_speak=True,
            mode="COMMAND",
        )
        self._record_history(command_id, command, out, start_time)
        if self._settings.debug_performance:
            logger.info("[AGENT] Command completed in %0.1fms", duration * 1000)
        return out

    def _record_history(
        self,
        command_id: str,
        command: str,
        output: AgentOutput,
        start_time: float,
    ) -> None:
        duration_ms = round((time.time() - start_time) * 1000, 1)
        record = CommandHistoryRecord(
            id=command_id,
            timestamp=time.time(),
            command=command,
            success=output.success,
            response=output.response,
            tool_calls=output.tool_calls,
            error=output.error,
            duration_ms=duration_ms,
        )
        get_command_history_store().add(record)
        get_event_bus().publish(
            EventType.COMMAND_COMPLETED,
            record.model_dump(),
        )

    # ── Error handling ────────────────────────────────────────────────────────

    def _handle_planner_error(self, exc: PlannerError, command: str) -> AgentOutput:
        """Convert a PlannerError into a user-friendly AgentOutput."""
        groq_error = getattr(exc, "groq_error", None)
        if groq_error is None:
            logger.error("Planner error (no Groq detail): %s", exc)
            return AgentOutput(
                success=False,
                response=f"Planning failed: {exc.message}",
                error=exc.message,
            )

        error_type = groq_error.error_type
        logger.error(
            "Groq API error [%s] for command %r: %s",
            error_type.value,
            command,
            groq_error.message,
        )

        if error_type == GroqErrorType.INVALID_API_KEY:
            msg = (
                "I can't connect to the AI service because the API key is invalid. "
                "Please check your GROQ_API_KEY in the .env file."
            )
        elif error_type == GroqErrorType.RATE_LIMIT:
            msg = (
                "The AI service is temporarily rate-limited. "
                "Please wait a moment and try again."
            )
        elif error_type == GroqErrorType.TIMEOUT:
            msg = "The AI service took too long to respond. Please try again."
        elif error_type == GroqErrorType.NETWORK:
            msg = (
                "I couldn't reach the AI service due to a network issue. "
                "Please check your internet connection."
            )
        elif error_type == GroqErrorType.MALFORMED_RESPONSE:
            msg = (
                "The AI service returned an unexpected response. "
                "Please try again or use a different command."
            )
        else:
            msg = f"An unexpected AI service error occurred: {groq_error.message}"

        return AgentOutput(
            success=False,
            response=msg,
            error=groq_error.message,
            metadata={"error_type": error_type.value, "retryable": groq_error.retryable},
        )

    async def approve_and_execute_task(self, task_id: str) -> dict[str, Any]:
        """
        Execute an approved multi-step plan through the SupervisorAgent and central ToolExecutor.
        """
        start_time = time.time()
        result = await self._supervisor.execute_approved_plan(task_id)
        task_mgr = get_task_manager()
        task = task_mgr.get_task(task_id)
        if task:
            out = AgentOutput(
                success=result.get("success", False),
                response=result.get("response", ""),
                tool_calls=[],
                error=result.get("error"),
            )
            self._record_history(task_id, task.description, out, start_time)
        return result

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        logger.info("PersonalAgent starting up (model=%s).", self._settings.groq_model)

    async def shutdown(self) -> None:
        logger.info("PersonalAgent shutting down.")


# ── Factory ───────────────────────────────────────────────────────────────────

def build_agent() -> PersonalAgent:
    """
    Wire all dependencies and return a ready PersonalAgent.
    Called once at application startup.
    """
    from app.agent.supervisor import SupervisorAgent
    from app.agent.tool_registry import get_tool_registry
    from app.security.audit import get_audit_logger
    from app.security.permissions import get_permission_checker
    from app.services.groq_client import get_groq_client

    groq_client = get_groq_client()
    registry = get_tool_registry()
    permission_checker = get_permission_checker()
    audit_logger = get_audit_logger()

    planner = GroqPlanner(groq_client=groq_client, registry=registry)
    executor = ToolExecutor(
        registry=registry,
        permission_checker=permission_checker,
        audit_logger=audit_logger,
    )
    supervisor = SupervisorAgent(
        groq_client=groq_client,
        registry=registry,
        executor=executor,
    )
    return PersonalAgent(planner=planner, executor=executor, supervisor=supervisor)
