"""
Tests for desktop control center API routes and WebSocket events.
"""
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.event_bus import AgentStatus, get_event_bus
from app.security.confirmation_manager import get_confirmation_manager


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_status(client):
    res = client.get("/agent/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "active_model" in data
    assert "detail" in data


def test_list_tools_enhanced(client):
    res = client.get("/agent/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    first_tool = data["tools"][0]
    assert "name" in first_tool
    assert "permission_level" in first_tool
    assert "requires_confirmation" in first_tool
    assert "parameters_schema" in first_tool


def test_system_metrics(client):
    res = client.get("/system/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "cpu_percent" in data
    assert "memory_percent" in data
    assert "disks" in data
    assert "top_processes" in data
    assert len(data["cpu_per_core"]) > 0


def test_memory_crud(client):
    # Set memory
    res = client.post("/agent/memory", json={"key": "test_pref", "value": {"theme": "dark"}})
    assert res.status_code == 200

    # Get memory
    res = client.get("/agent/memory")
    assert res.status_code == 200
    data = res.json()
    assert "test_pref" in data
    assert data["test_pref"]["theme"] == "dark"

    # Delete key
    res = client.delete("/agent/memory/test_pref")
    assert res.status_code == 200

    res = client.get("/agent/memory")
    assert "test_pref" not in res.json()


def test_confirmation_tickets(client):
    mgr = get_confirmation_manager()
    ticket = mgr.create_ticket(
        tool_name="delete_folder",
        arguments={"path": "C:/fake_path"},
        command="delete fake folder",
    )

    # Check pending
    res = client.get("/agent/confirmations/pending")
    assert res.status_code == 200
    tickets = res.json()
    assert any(t["ticket_id"] == ticket.ticket_id for t in tickets)

    # Respond to ticket
    res = client.post(f"/agent/confirmations/{ticket.ticket_id}/respond", json={"approved": True})
    assert res.status_code == 200
    assert res.json()["approved"] is True

    # Check no longer pending
    res = client.get("/agent/confirmations/pending")
    assert not any(t["ticket_id"] == ticket.ticket_id for t in res.json())


def test_security_settings(client):
    res = client.get("/agent/security/settings")
    assert res.status_code == 200
    data = res.json()
    assert "allowed_base_paths" in data
    assert "allow_shell_commands" in data
    assert "risk_policies" in data


def test_audit_logs(client):
    res = client.get("/agent/logs/audit")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_agent_config(client):
    res = client.get("/agent/config")
    assert res.status_code == 200
    data = res.json()
    assert "groq_model" in data

    # Update config
    res = client.post("/agent/config", json={"wake_word": "Jarvis2"})
    assert res.status_code == 200
    assert res.json()["config"]["wake_word"] == "Jarvis2"

    # Revert
    client.post("/agent/config", json={"wake_word": "Jarvis"})


def test_history_crud(client):
    res = client.get("/agent/history")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res = client.delete("/agent/history")
    assert res.status_code == 200
    assert res.json()["status"] == "cleared"


def test_voice_listen_endpoint(client):
    """
    POST /agent/voice/listen — should always return a well-formed JSON response.
    In CI (no real mic) it will return success:False with a friendly error message.
    In a live environment with a mic it may return success:True with a transcript.
    Either way the response must contain the 'success' key.
    """
    res = client.post("/agent/voice/listen")
    assert res.status_code == 200
    data = res.json()
    assert "success" in data
    if not data["success"]:
        # Must include a readable error string (not a Python traceback or None)
        assert "error" in data and isinstance(data["error"], str) and len(data["error"]) > 0

