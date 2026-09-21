"""
FastAPI application factory with lifespan context manager.

The agent singleton is stored on `app.state` so it can be accessed
by route dependencies without global mutable variables.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.error_handler import GlobalExceptionMiddleware
from app.api.middleware.rate_limiter import RateLimitMiddleware
from app.api.middleware.request_id import RequestIDMiddleware
from app.api.router import api_router
from app.config.settings import get_settings
from app.services.event_bus import get_event_bus
from app.services.groq_client import get_groq_client
from app.utils.logger import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup → serve → shutdown."""
    # ── Startup ───────────────────────────────────────────────────────────────
    configure_logging()
    logger.info("Starting personal-ai-agent …")

    # Load all tool modules into the agent's registry
    from app.agent.tool_registry import load_all_tools
    load_all_tools()

    # Build and warm up agent
    from app.agent.agent import build_agent
    agent = build_agent()
    await agent.startup()
    app.state.agent = agent

    logger.info("personal-ai-agent is ready.")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down personal-ai-agent …")
    try:
        if hasattr(app.state, "agent") and app.state.agent:
            await app.state.agent.shutdown()
    except Exception as exc:
        logger.warning("Error during agent shutdown: %s", exc)

    try:
        await get_groq_client().close()
    except Exception as exc:
        logger.warning("Error closing GroqClient: %s", exc)

    try:
        await get_event_bus().close_all()
    except Exception as exc:
        logger.warning("Error closing WebSocket connections: %s", exc)

    logger.info("personal-ai-agent shutdown complete.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="A production-ready personal AI computer agent powered by Groq.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Middleware execution pipeline:
    # Incoming: CORS -> RequestID -> GlobalException -> RateLimit -> Endpoint
    # Outgoing: Endpoint -> RateLimit -> GlobalException -> RequestID -> CORS
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(GlobalExceptionMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)
    return app


# ── WSGI/ASGI entry point ─────────────────────────────────────────────────────
app = create_app()
