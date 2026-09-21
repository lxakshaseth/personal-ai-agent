"""
Test: GET /health endpoint.
"""
import pytest
from fastapi.testclient import TestClient

# Patch settings before importing the app so GROQ_API_KEY validation passes
import os
os.environ.setdefault("GROQ_API_KEY", "test_key_for_ci")

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Synchronous TestClient (does NOT start the full lifespan)."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body(client: TestClient) -> None:
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "personal-ai-agent"
    assert "version" in data


def test_health_content_type(client: TestClient) -> None:
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
