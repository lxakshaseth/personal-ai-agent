"""
Request ID tracking middleware and context manager.
Attaches X-Request-ID header to every HTTP response and maintains contextvars correlation ID.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve the current request correlation ID, or empty string if not in an HTTP context."""
    return _REQUEST_ID_CTX.get()


def set_request_id(request_id: str) -> None:
    """Set the current request correlation ID in the contextvar."""
    _REQUEST_ID_CTX.set(request_id)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that reads an existing X-Request-ID header from incoming requests,
    or generates a new UUIDv4 if missing, and attaches it to response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
        if not req_id:
            req_id = f"req_{uuid.uuid4().hex[:12]}"

        token = _REQUEST_ID_CTX.set(req_id)
        # Store on request.state as well
        request.state.request_id = req_id

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            _REQUEST_ID_CTX.reset(token)
