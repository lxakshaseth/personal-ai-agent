"""
Comprehensive Agent API routes for the Windows Desktop Control Center.
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.agent.agent import PersonalAgent
from app.agent.base import AgentInput
from app.agent.history import CommandHistoryRecord, get_command_history_store
from app.config.settings import get_settings
from app.memory.store import get_memory_store
from app.security.confirmation_manager import ConfirmationTicket, get_confirmation_manager
from app.services.event_bus import AgentStatus, EventType, get_event_bus
from app.utils.exceptions import AgentBaseError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])


# ── Request / Response Models ─────────────────────────────────────────────────

class RunCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Natural-language command")
    confirmed: bool = Field(
        default=False,
        description="Set to true to pre-confirm HIGH-risk tool execution",
    )
    session_id: str | None = Field(default=None, description="Optional session ID")
    client_speaks: bool = Field(
        default=False,
        description="If True, client UI handles speech synthesis; backend skips host TTS to avoid duplicate audio.",
    )


class ToolCallInfo(BaseModel):
    tool: str
    args: dict[str, Any]
    success: bool
    output: str
    error: str | None


class RunCommandResponse(BaseModel):
    success: bool
    response: str
    tool_calls: list[ToolCallInfo]
    error: str | None = None


class ToolInfo(BaseModel):
    name: str
    description: str
    permission_level: str
    requires_confirmation: bool = False
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    count: int
    tools: list[ToolInfo]


class ExecuteToolRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ExecuteToolResponse(BaseModel):
    tool: str
    success: bool
    output: str
    error: str | None = None


class StatusResponse(BaseModel):
    status: str
    detail: str
    active_model: str
    voice_enabled: bool
    stt_provider: str
    tts_provider: str
    wake_word: str
    wake_word_enabled: bool


class RespondConfirmationRequest(BaseModel):
    approved: bool


class MemoryItem(BaseModel):
    key: str
    value: Any
    ttl: int | None = None


class SecuritySettingsResponse(BaseModel):
    allowed_base_paths: list[str]
    allow_shell_commands: bool
    require_confirmation: bool
    allow_file_deletion: bool
    allow_browser_automation: bool
    allow_whatsapp_messaging: bool
    allow_system_controls: bool
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_commands: list[str]
    risk_policies: dict[str, str]


class UpdateSecuritySettingsRequest(BaseModel):
    allow_shell_commands: bool | None = None
    allow_file_deletion: bool | None = None
    allow_browser_automation: bool | None = None
    allow_whatsapp_messaging: bool | None = None
    allow_system_controls: bool | None = None
    require_confirmation: bool | None = None
    disabled_tools: list[str] | None = None


class ConfigUpdateRequest(BaseModel):
    groq_model: str | None = None
    stt_provider: str | None = None
    tts_provider: str | None = None
    wake_word: str | None = None
    wake_word_enabled: bool | None = None
    voice_enabled: bool | None = None


class SpeakRequest(BaseModel):
    text: str


# ── Dependency ────────────────────────────────────────────────────────────────

def _get_agent(request: Request) -> PersonalAgent:
    """FastAPI dependency that returns the app-level agent singleton."""
    return request.app.state.agent


# ── Agent Execution & Status Routes ───────────────────────────────────────────

@router.post("/run", response_model=RunCommandResponse)
async def run_command(
    body: RunCommandRequest,
    agent: PersonalAgent = Depends(_get_agent),
) -> RunCommandResponse:
    """Execute a natural-language command through the AI agent."""
    agent_input = AgentInput(
        command=body.command,
        confirmed=body.confirmed,
        session_id=body.session_id,
    )
    try:
        output = await agent.run(agent_input)
    except AgentBaseError as exc:
        logger.exception("Agent error processing command %r", body.command)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    tool_calls = [ToolCallInfo(**tc) for tc in output.tool_calls]

    # Non-blocking async TTS: UI receives text immediately, audio plays concurrently
    # (Skipped if client_speaks is True, e.g. web/desktop UI handles browser synthesis)
    settings = get_settings()
    if (
        not body.client_speaks
        and settings.voice_enabled
        and getattr(output, "should_speak", True)
        and output.response
    ):
        from app.voice.voice_response_service import get_voice_service
        get_voice_service().speak_async(output.response)

    return RunCommandResponse(
        success=output.success,
        response=output.response,
        tool_calls=tool_calls,
        error=output.error,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get current agent operational status and configuration."""
    settings = get_settings()
    bus = get_event_bus()
    return StatusResponse(
        status=bus.current_status.value,
        detail=bus.status_detail,
        active_model=settings.groq_model,
        voice_enabled=settings.voice_enabled,
        stt_provider=settings.stt_provider,
        tts_provider=settings.tts_provider,
        wake_word=settings.wake_word,
        wake_word_enabled=settings.wake_word_enabled,
    )


# ── Tool Management Routes ───────────────────────────────────────────────────

@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """List all registered tools with permissions and schemas."""
    from app.agent.tool_registry import get_tool_registry

    registry = get_tool_registry()
    tools = [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            permission_level=tool.permission_level.value,
            requires_confirmation=getattr(tool, "requires_confirmation", False),
            parameters_schema=getattr(tool, "parameters_schema", {}),
        )
        for tool in registry.all()
    ]
    return ToolListResponse(count=len(tools), tools=tools)


@router.post("/tools/{tool_name}/execute", response_model=ExecuteToolResponse)
async def execute_tool_directly(
    tool_name: str,
    body: ExecuteToolRequest,
    agent: PersonalAgent = Depends(_get_agent),
) -> ExecuteToolResponse:
    """Directly test or execute a specific tool with arguments."""
    from app.agent.schemas import ToolCallPlan

    plan = ToolCallPlan(
        tool_name=tool_name,
        arguments=body.args,
        tool_call_id="direct_exec",
    )
    records = await agent._executor.execute_plan(
        [plan],
        command=f"Manual execution of {tool_name}",
        confirmed=body.confirmed,
    )
    if not records:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' could not be executed.")

    rec = records[0]
    return ExecuteToolResponse(
        tool=tool_name,
        success=rec.result.success,
        output=rec.result.output,
        error=rec.result.error,
    )


# ── Confirmation Dialog Routes ───────────────────────────────────────────────

@router.get("/confirmations/pending", response_model=list[ConfirmationTicket])
async def list_pending_confirmations() -> list[ConfirmationTicket]:
    """List all pending HIGH-risk confirmation tickets."""
    return get_confirmation_manager().list_pending_tickets()


@router.post("/confirmations/{ticket_id}/respond")
async def respond_confirmation(
    ticket_id: str,
    body: RespondConfirmationRequest,
) -> dict[str, Any]:
    """Approve or reject a pending HIGH-risk operation."""
    success = get_confirmation_manager().respond(ticket_id, approved=body.approved)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found or already expired/resolved.",
        )
    return {"status": "ok", "ticket_id": ticket_id, "approved": body.approved}


# ── Command History Routes ───────────────────────────────────────────────────

@router.get("/history", response_model=list[CommandHistoryRecord])
async def get_history() -> list[CommandHistoryRecord]:
    """Retrieve chronological history of user commands."""
    return get_command_history_store().all()


@router.delete("/history")
async def clear_history() -> dict[str, str]:
    """Clear all command execution history."""
    get_command_history_store().clear()
    return {"status": "cleared"}


# ── Memory Management Routes ─────────────────────────────────────────────────

@router.get("/memory")
async def get_all_memory() -> dict[str, Any]:
    """Retrieve all short-term key-value memory pairs."""
    store = get_memory_store()
    return await store.list_all()


@router.post("/memory")
async def set_memory(item: MemoryItem) -> dict[str, str]:
    """Set a key-value pair in agent memory."""
    store = get_memory_store()
    await store.set(item.key, item.value, ttl=item.ttl)
    return {"status": "stored", "key": item.key}


@router.delete("/memory/{key}")
async def delete_memory(key: str) -> dict[str, str]:
    """Delete a key from agent memory."""
    store = get_memory_store()
    await store.delete(key)
    return {"status": "deleted", "key": key}


@router.delete("/memory")
async def clear_memory() -> dict[str, str]:
    """Clear all memory entries."""
    store = get_memory_store()
    await store.clear()
    return {"status": "cleared"}


# ── Security & Audit Routes ───────────────────────────────────────────────────

@router.get("/security/settings", response_model=SecuritySettingsResponse)
async def get_security_settings() -> SecuritySettingsResponse:
    """Retrieve active security configurations and sandboxing boundaries."""
    settings = get_settings()
    if isinstance(settings.allowed_commands, list):
        allowed_cmds = [str(c) for c in settings.allowed_commands]
    else:
        allowed_cmds = [c.strip() for c in str(settings.allowed_commands).split(",") if c.strip()]
    return SecuritySettingsResponse(
        allowed_base_paths=settings.allowed_base_paths,
        allow_shell_commands=settings.allow_shell_commands,
        require_confirmation=settings.agent_require_confirmation,
        allow_file_deletion=settings.allow_file_deletion,
        allow_browser_automation=settings.allow_browser_automation,
        allow_whatsapp_messaging=settings.allow_whatsapp_messaging,
        allow_system_controls=settings.allow_system_controls,
        disabled_tools=settings.disabled_tools or [],
        allowed_commands=allowed_cmds,
        risk_policies={
            "LOW": "Read-only and benign operations; no confirmation required.",
            "MEDIUM": "Modifying operations within allowed sandboxes; automatic execution.",
            "HIGH": "Destructive or dangerous actions (deletion, restart, terminal); requires confirmation.",
        },
    )


@router.post("/security/settings", response_model=SecuritySettingsResponse)
async def update_security_settings(body: UpdateSecuritySettingsRequest) -> SecuritySettingsResponse:
    """Update runtime security controls."""
    settings = get_settings()
    if body.allow_shell_commands is not None:
        settings.allow_shell_commands = body.allow_shell_commands
    if body.allow_file_deletion is not None:
        settings.allow_file_deletion = body.allow_file_deletion
    if body.allow_browser_automation is not None:
        settings.allow_browser_automation = body.allow_browser_automation
    if body.allow_whatsapp_messaging is not None:
        settings.allow_whatsapp_messaging = body.allow_whatsapp_messaging
    if body.allow_system_controls is not None:
        settings.allow_system_controls = body.allow_system_controls
    if body.require_confirmation is not None:
        settings.agent_require_confirmation = body.require_confirmation
    if body.disabled_tools is not None:
        settings.disabled_tools = body.disabled_tools
    return await get_security_settings()


# ── Task Management Routes ────────────────────────────────────────────────────

@router.get("/tasks")
async def list_tasks(state: str | None = None) -> list[dict[str, Any]]:
    """List all recent and active agent tasks with optional state filter."""
    from app.agent.tasks import get_task_manager
    tasks = get_task_manager().list_tasks(state_filter=state)
    return [t.model_dump() for t in tasks]


@router.get("/tasks/active")
async def get_active_task() -> dict[str, Any] | None:
    """Get currently active/running task."""
    from app.agent.tasks import get_task_manager
    task = get_task_manager().get_active_task()
    return task.model_dump() if task else None


@router.get("/tasks/{task_id}")
async def get_task_by_id(task_id: str) -> dict[str, Any]:
    """Get full details of a specific task."""
    from app.agent.tasks import get_task_manager
    task = get_task_manager().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found.")
    return task.model_dump()


@router.post("/tasks/{task_id}/approve")
async def approve_task_plan(
    task_id: str,
    agent: PersonalAgent = Depends(_get_agent),
) -> dict[str, Any]:
    """Approve and execute a multi-step plan for a task in WAITING_APPROVAL state."""
    result = await agent.approve_and_execute_task(task_id)
    if not result.get("success") and "not found" in result.get("error", "").lower():
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str) -> dict[str, Any]:
    """Pause an active agent task."""
    from app.agent.tasks import get_task_manager
    success = get_task_manager().pause_task(task_id)
    return {"status": "paused" if success else "failed", "task_id": task_id}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str) -> dict[str, Any]:
    """Resume a paused agent task."""
    from app.agent.tasks import get_task_manager
    success = get_task_manager().resume_task(task_id)
    return {"status": "resumed" if success else "failed", "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, Any]:
    """Cancel a running or paused agent task."""
    from app.agent.tasks import get_task_manager
    success = get_task_manager().cancel_task(task_id)
    return {"status": "cancelled" if success else "failed", "task_id": task_id}


@router.post("/stop")
@router.post("/cancel")
@router.post("/tasks/cancel_active")
async def stop_or_cancel_active_task() -> dict[str, Any]:
    """
    Global interrupt & stop (ESC or Stop button):
    Cancels the active agent task and immediately stops ongoing TTS speech playback.
    """
    from app.agent.tasks import get_task_manager
    from app.services.event_bus import AgentStatus, get_event_bus
    from app.voice.voice_response_service import get_voice_service

    # 1. Stop active audio immediately
    get_voice_service().stop()

    # 2. Cancel active agent task
    task_cancelled = get_task_manager().cancel_active_task()

    # 3. Transition agent state back to IDLE
    bus = get_event_bus()
    bus.set_status(AgentStatus.ONLINE, "Ready")
    bus.publish_event("agent.state", {"state": "IDLE", "detail": "Stopped by user"})

    return {
        "status": "stopped",
        "task_cancelled": task_cancelled,
    }


@router.get("/logs/audit")
async def get_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve the most recent entries from the append-only audit log."""
    settings = get_settings()
    audit_file = Path(settings.audit_log_file)
    if not audit_file.exists():
        return []

    lines: list[str] = []
    try:
        with audit_file.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []

    records: list[dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


# ── Settings Configuration Routes ─────────────────────────────────────────────

@router.get("/config")
async def get_agent_config() -> dict[str, Any]:
    """Retrieve current agent system configuration."""
    settings = get_settings()
    return {
        "groq_model": settings.groq_model,
        "stt_provider": settings.stt_provider,
        "tts_provider": settings.tts_provider,
        "voice_enabled": settings.voice_enabled,
        "wake_word": settings.wake_word,
        "wake_word_enabled": settings.wake_word_enabled,
        "allow_shell_commands": settings.allow_shell_commands,
        "require_confirmation": settings.agent_require_confirmation,
    }


@router.post("/config")
async def update_agent_config(body: ConfigUpdateRequest) -> dict[str, Any]:
    """Update runtime agent settings."""
    settings = get_settings()
    if body.groq_model is not None:
        settings.groq_model = body.groq_model
    if body.stt_provider is not None:
        settings.stt_provider = body.stt_provider
    if body.tts_provider is not None:
        settings.tts_provider = body.tts_provider
    if body.wake_word is not None:
        settings.wake_word = body.wake_word
    if body.wake_word_enabled is not None:
        settings.wake_word_enabled = body.wake_word_enabled
    if body.voice_enabled is not None:
        settings.voice_enabled = body.voice_enabled

    return {"status": "updated", "config": await get_agent_config()}


# ── Voice Trigger Routes ──────────────────────────────────────────────────────

@router.post("/voice/speak")
async def speak_text(body: SpeakRequest) -> dict[str, str]:
    """Trigger speech output using the configured TTS provider."""
    from app.voice.text_to_speech import get_tts_provider

    bus = get_event_bus()
    bus.publish(EventType.VOICE_EVENT, {"action": "speaking", "text": body.text})
    provider = get_tts_provider()
    await provider.speak(body.text)
    return {"status": "spoken", "text": body.text}


@router.post("/voice/listen")
async def trigger_listen(agent: PersonalAgent = Depends(_get_agent)) -> dict[str, Any]:
    """Trigger an on-demand microphone capture and process through agent."""
    from app.voice.microphone import MicrophoneRecorder
    from app.voice.speech_to_text import get_stt_provider
    from app.voice.text_to_speech import get_tts_provider
    from app.utils.exceptions import MicrophoneUnavailableError, NoSpeechDetectedError, VoiceTimeoutError

    bus = get_event_bus()
    voice_req_id = str(uuid.uuid4())

    recorder = MicrophoneRecorder()
    if not recorder.is_available():
        logger.info("Voice listen requested, but no microphone is available on host.")
        bus.set_status(AgentStatus.ONLINE, "Ready (No microphone detected)")
        bus.publish(EventType.VOICE_EVENT, {"action": "error", "error": "No microphone detected"})
        bus.publish_event("agent.error", {
            "error": "No microphone detected on host system. Please connect a microphone or use keyboard text input.",
            "request_id": voice_req_id,
        })
        return {
            "success": False,
            "error": "No microphone detected on your system. Please connect an audio input device or type your command.",
        }

    bus.set_status(AgentStatus.LISTENING, "Listening for voice command...")
    bus.publish(EventType.VOICE_EVENT, {"action": "listening"})
    bus.publish_event("agent.listening", {"request_id": voice_req_id})

    try:
        audio = await recorder.record_phrase(timeout=5.0, phrase_time_limit=7.0)
    except (MicrophoneUnavailableError, NoSpeechDetectedError, VoiceTimeoutError) as e:
        bus.set_status(AgentStatus.ONLINE, "Ready")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning("Microphone recording error: %s", e)
        bus.set_status(AgentStatus.ONLINE, "Ready")
        return {"success": False, "error": f"Audio capture error: {e}"}

    if not audio:
        bus.set_status(AgentStatus.ONLINE, "Ready")
        return {"success": False, "error": "No speech detected."}

    try:
        stt = get_stt_provider()
        bus.set_status(AgentStatus.THINKING, "Transcribing speech...")
        bus.publish(EventType.VOICE_EVENT, {"action": "transcribing"})
        bus.publish_event("agent.transcribing", {"request_id": voice_req_id})
        stt_res = await stt.transcribe(audio)
        text = stt_res.text.strip()
    except Exception as e:
        logger.warning("STT transcription error: %s", e)
        bus.set_status(AgentStatus.ONLINE, "Ready")
        return {"success": False, "error": f"Transcription error: {e}"}

    if not text:
        bus.set_status(AgentStatus.ONLINE, "Ready")
        return {"success": False, "error": "Could not recognize speech."}

    bus.publish(EventType.VOICE_EVENT, {"action": "transcribed", "text": text})

    # Run command
    bus.set_status(AgentStatus.EXECUTING, f"Executing: {text[:30]}...")
    out = await agent.run(AgentInput(command=text))

    # Non-blocking async speech output: UI receives response immediately, speech plays concurrently
    if out.response:
        from app.voice.voice_response_service import get_voice_service
        get_voice_service().speak_async(out.response, request_id=voice_req_id)

    return {
        "success": out.success,
        "transcript": text,
        "response": out.response,
        "tool_calls": out.tool_calls,
        "speak": True,
    }
