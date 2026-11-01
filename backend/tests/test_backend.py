"""
Unit Tests for Backend API Gateway
Assigned Member: Apeksha KT (feature/backend-fastapi - Task W5)
"""
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify that the health check endpoint returns 200 and healthy status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    # Verify request logging middleware attached the response time header
    assert "X-Response-Time" in response.headers


def test_chat_endpoint_pending():
    """Verify that chat endpoint returns 501 Not Implemented."""
    response = client.post(
        "/api/v1/ai/chat",
        json={"session_id": "session-123", "message": "Hello AI voicebot"},
    )
    assert response.status_code == 501
    assert "Chat endpoint implementation pending" in response.json()["detail"]
