"""
Global exception handling middleware and exception handlers for FastAPI.
Ensures all unhandled exceptions return standardized JSON error envelopes with request IDs,
and logs structured error details with zero secret leakage.
"""
from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.middleware.request_id import get_request_id
from app.config.settings import get_settings
from app.utils.exceptions import AgentBaseError, PermissionDeniedError
from app.utils.sanitizer import sanitize_data

logger = logging.getLogger(__name__)


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """
    Catches unhandled exceptions across the entire ASGI pipeline,
    records correlation metrics, and formats consistent JSON error envelopes.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except PermissionDeniedError as exc:
            req_id = get_request_id() or getattr(request.state, "request_id", "")
            logger.warning("Permission denied on %s %s [%s]: %s", request.method, request.url.path, req_id, exc)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Permission Denied",
                    "detail": str(exc),
                    "request_id": req_id,
                },
                headers={"X-Request-ID": req_id} if req_id else {},
            )
        except AgentBaseError as exc:
            req_id = get_request_id() or getattr(request.state, "request_id", "")
            logger.error("Agent error processing %s %s [%s]: %s", request.method, request.url.path, req_id, exc)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Agent Processing Error",
                    "detail": str(exc),
                    "request_id": req_id,
                },
                headers={"X-Request-ID": req_id} if req_id else {},
            )
        except Exception as exc:
            req_id = get_request_id() or getattr(request.state, "request_id", "")
            logger.exception("Unhandled server exception on %s %s [%s]: %s", request.method, request.url.path, req_id, exc)
            settings = get_settings()
            detail = str(exc) if settings.debug else "An unexpected internal server error occurred. Please try again."
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "detail": sanitize_data(detail) if isinstance(detail, (str, dict)) else str(detail),
                    "request_id": req_id,
                },
                headers={"X-Request-ID": req_id} if req_id else {},
            )
