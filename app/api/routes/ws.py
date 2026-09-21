"""
WebSocket endpoint for real-time bi-directional streaming between desktop UI and agent.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.security.confirmation_manager import get_confirmation_manager
from app.services.event_bus import AgentStatus, EventType, get_event_bus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket) -> None:
    """Bi-directional WebSocket connection for desktop real-time synchronization."""
    await websocket.accept()
    bus = get_event_bus()
    conf_mgr = get_confirmation_manager()
    bus.register_client(websocket)

    try:
        # Send initial state snapshot
        initial_payload = {
            "type": "init_snapshot",
            "payload": {
                "status": bus.current_status.value,
                "detail": bus.status_detail,
                "pending_confirmations": [t.model_dump() for t in conf_mgr.list_pending_tickets()],
                "recent_events": bus.get_recent_events()[-20:],
            },
        }
        await websocket.send_text(json.dumps(initial_payload))

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                payload = msg.get("payload", {})

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "respond_confirmation":
                    ticket_id = payload.get("ticket_id")
                    approved = bool(payload.get("approved", False))
                    if ticket_id:
                        conf_mgr.respond(ticket_id, approved)

                elif msg_type == "approve_task":
                    task_id = payload.get("task_id")
                    if task_id:
                        agent = getattr(websocket.app.state, "agent", None)
                        if agent:
                            import asyncio
                            asyncio.create_task(agent.approve_and_execute_task(task_id))

                elif msg_type in ("cancel", "cancel_task"):
                    from app.agent.tasks import get_task_manager
                    task_id = payload.get("task_id")
                    if task_id:
                        get_task_manager().cancel_task(task_id)
                    else:
                        get_task_manager().cancel_active_task()

                elif msg_type == "set_status":
                    status_str = payload.get("status")
                    detail = payload.get("detail", "")
                    if status_str:
                        try:
                            status_enum = AgentStatus(status_str)
                            bus.set_status(status_enum, detail)
                        except ValueError:
                            pass

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.debug("Desktop UI WebSocket disconnected.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        bus.unregister_client(websocket)
