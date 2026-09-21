"""
Confirmation ticket manager for interactive approval of HIGH-risk operations.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.services.event_bus import EventType, get_event_bus

logger = logging.getLogger(__name__)


class ConfirmationTicket(BaseModel):
    ticket_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    arguments: dict[str, Any]
    command: str = ""
    reason: str = "This operation carries a HIGH risk level and requires your approval."
    status: str = "pending"  # pending, approved, rejected, expired
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 120.0)


class ConfirmationManager:
    """Tracks and resolves pending confirmation tickets."""

    def __init__(self) -> None:
        self._tickets: dict[str, ConfirmationTicket] = {}
        self._waiters: dict[str, asyncio.Future[bool]] = {}

    def create_ticket(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        command: str = "",
        reason: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> ConfirmationTicket:
        """Create a new confirmation ticket and broadcast to desktop UI."""
        ticket_id = str(uuid.uuid4())
        ticket = ConfirmationTicket(
            ticket_id=ticket_id,
            tool_name=tool_name,
            arguments=arguments,
            command=command,
            reason=reason or f"Executing '{tool_name}' requires explicit confirmation.",
            created_at=time.time(),
            expires_at=time.time() + timeout_seconds,
        )
        self._tickets[ticket_id] = ticket

        # Broadcast event
        get_event_bus().publish(
            EventType.CONFIRMATION_REQUESTED,
            ticket.model_dump(),
        )
        logger.info("Created confirmation ticket %s for tool %s", ticket_id, tool_name)
        return ticket

    def list_pending_tickets(self) -> list[ConfirmationTicket]:
        """Return all active, non-expired pending tickets."""
        now = time.time()
        pending: list[ConfirmationTicket] = []
        for t in self._tickets.values():
            if t.status == "pending":
                if t.expires_at > now:
                    pending.append(t)
                else:
                    t.status = "expired"
        return pending

    def get_ticket(self, ticket_id: str) -> ConfirmationTicket | None:
        return self._tickets.get(ticket_id)

    def respond(self, ticket_id: str, approved: bool) -> bool:
        """Resolve a pending confirmation ticket."""
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False

        if ticket.status != "pending":
            return False

        if time.time() > ticket.expires_at:
            ticket.status = "expired"
            return False

        ticket.status = "approved" if approved else "rejected"

        # Resolve any waiter
        waiter = self._waiters.pop(ticket_id, None)
        if waiter and not waiter.done():
            waiter.set_result(approved)

        # Broadcast resolution
        get_event_bus().publish(
            EventType.CONFIRMATION_RESOLVED,
            {
                "ticket_id": ticket_id,
                "tool_name": ticket.tool_name,
                "approved": approved,
                "status": ticket.status,
            },
        )
        logger.info("Resolved ticket %s: approved=%s", ticket_id, approved)
        return True

    async def wait_for_response(self, ticket_id: str, timeout: float = 120.0) -> bool:
        """Async wait until a user approves/rejects the ticket in desktop UI."""
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status != "pending":
            return False

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._waiters[ticket_id] = future

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            ticket.status = "expired"
            self._waiters.pop(ticket_id, None)
            return False


# ── Global Singleton ─────────────────────────────────────────────────────────

_confirmation_manager: ConfirmationManager | None = None


def get_confirmation_manager() -> ConfirmationManager:
    global _confirmation_manager
    if _confirmation_manager is None:
        _confirmation_manager = ConfirmationManager()
    return _confirmation_manager
