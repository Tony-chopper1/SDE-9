"""
Unit Tests for Backend API Gateway
Assigned Member: Apeksha KT (feature/backend-fastapi - Task W5)
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import app, unexpected_exception_handler

client = TestClient(app)

# Separate test application for checking unexpected server errors.
error_test_app = FastAPI()


@error_test_app.exception_handler(Exception)
async def handle_test_exception(request, exc):
    return await unexpected_exception_handler(request, exc)


@error_test_app.get("/test-error")
def trigger_test_error():
    raise RuntimeError("Sensitive internal database information")


error_client = TestClient(
    error_test_app,
    raise_server_exceptions=False,
)


def test_health_check_endpoint():
    """Verify that the health check endpoint returns 200 and healthy status."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert "X-Response-Time" in response.headers
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Correlation-ID"]


def test_readiness_endpoint():
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "ready"


def test_versioned_readiness_endpoint():
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"


def test_request_and_correlation_id_headers():
    response = client.get(
        "/api/v1/health",
        headers={
            "X-Request-ID": "test-request-123",
            "X-Correlation-ID": "test-correlation-456",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Correlation-ID"] == "test-correlation-456"


def test_correlation_id_defaults_to_request_id():
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "shared-id-123"},
    )

    assert response.headers["X-Request-ID"] == "shared-id-123"
    assert response.headers["X-Correlation-ID"] == "shared-id-123"


def test_chat_endpoint_pending():
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "session_id": "session-123",
            "message": "Hello AI voicebot",
        },
    )

    assert response.status_code == 501

    error = response.json()["error"]

    assert response.json()["success"] is False
    assert error["code"] == "HTTP_501"
    assert error["message_safe_for_user"]
    assert error["retryable"] is True
    assert error["correlation_id"]
    assert "message" not in error
    assert "request_id" not in error


def test_unexpected_error_does_not_leak_internal_details():
    response = error_client.get("/test-error")

    assert response.status_code == 500

    error = response.json()["error"]

    assert error["code"] == "INTERNAL_SERVER_ERROR"
    assert error["message_safe_for_user"] == (
        "An unexpected server error occurred"
    )
    assert error["retryable"] is True
    assert error["correlation_id"]

    assert "Sensitive internal database information" not in response.text