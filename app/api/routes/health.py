from pathlib import Path
from typing import Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config.settings import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """
    Returns a simple liveness check.

    Response:
        {"status": "ok", "service": "personal-ai-agent", "version": "0.1.0"}
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/ready", tags=["Health"])
async def readiness_check() -> JSONResponse:
    """
    Readiness probe validating subsystem health:
    - Tool registry count
    - LLM configuration & circuit breaker state
    - Storage / log filesystem permissions
    - Real-time event bus
    """
    settings = get_settings()
    from app.agent.tool_registry import get_tool_registry
    from app.services.event_bus import get_event_bus
    from app.services.groq_client import get_groq_client

    checks: dict[str, Any] = {}
    is_ready = True

    # 1. Tool Registry
    tools = get_tool_registry().list_tools()
    tool_count = len(tools)
    tool_status = tool_count >= 5
    checks["tools"] = {
        "status": "ok" if tool_status else "degraded",
        "count": tool_count,
    }
    if not tool_status:
        is_ready = False

    # 2. LLM / Groq status
    groq_client = get_groq_client()
    has_api_key = bool(settings.groq_api_key and settings.groq_api_key.strip())
    circuit_state = groq_client._circuit_breaker.state.value
    groq_ok = has_api_key and circuit_state != "open"
    checks["llm"] = {
        "status": "ok" if groq_ok else "unhealthy",
        "provider": "groq",
        "model": settings.groq_model,
        "circuit_breaker": circuit_state,
        "api_key_configured": has_api_key,
    }
    if not groq_ok:
        is_ready = False

    # 3. Storage filesystem writable check
    try:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        test_file = log_dir / ".write_check"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        checks["storage"] = {"status": "ok", "writable": True}
    except Exception as exc:
        checks["storage"] = {"status": "error", "error": str(exc)}
        is_ready = False

    # 4. Event Bus
    bus = get_event_bus()
    checks["event_bus"] = {
        "status": "ok",
        "agent_status": bus.current_status.value,
    }

    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "service": settings.app_name,
            "version": settings.app_version,
            "checks": checks,
        },
    )

