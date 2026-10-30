"""
Unit Tests for Backend API Gateway
Assigned Member: Apeksha KT (feature/backend-fastapi - Task W5)

TODO (Apeksha KT):
Write unit tests for FastAPI endpoints (health, sessions, chat) to achieve >80% coverage.
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


# TODO (Apeksha KT): Uncomment and implement after implementing routes in backend/main.py
# def test_create_and_get_session():
#     res = client.post("/api/v1/sessions", json={})
#     assert res.status_code == 201
#     ...
