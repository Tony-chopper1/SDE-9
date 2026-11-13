
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_create_session():
    response = client.post(
        "/api/v1/sessions",
        json={"user_id": "student01"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "created"


def test_get_all_sessions():
    response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_session_by_id():
    create_response = client.post(
        "/api/v1/sessions",
        json={"user_id": "student02"},
    )

    session_id = create_response.json()["session_id"]

    response = client.get(f"/api/v1/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_get_session_not_found():
    non_existent_id = uuid4()

    response = client.get(
        f"/api/v1/sessions/{non_existent_id}"
    )

    assert response.status_code == 404

    error = response.json()["error"]

    assert response.json()["success"] is False
    assert error["code"] == "HTTP_404"
    assert error["message_safe_for_user"] == "Resource not found"
    assert error["retryable"] is False
    assert error["correlation_id"]
    assert "request_id" not in error


def test_pause_session():
    create_response = client.post(
        "/api/v1/sessions",
        json={"user_id": "student03"},
    )

    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/pause"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "paused"


def test_pause_session_not_found():
    non_existent_id = uuid4()

    response = client.post(
        f"/api/v1/sessions/{non_existent_id}/pause"
    )

    assert response.status_code == 404

    error = response.json()["error"]

    assert response.json()["success"] is False
    assert error["code"] == "HTTP_404"
    assert error["message_safe_for_user"] == "Resource not found"
    assert error["correlation_id"]


def test_stop_session():
    create_response = client.post(
        "/api/v1/sessions",
        json={"user_id": "student04"},
    )

    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/stop"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_stop_session_not_found():
    non_existent_id = uuid4()

    response = client.post(
        f"/api/v1/sessions/{non_existent_id}/stop"
    )

    assert response.status_code == 404

    error = response.json()["error"]

    assert response.json()["success"] is False
    assert error["code"] == "HTTP_404"
    assert error["message_safe_for_user"] == "Resource not found"
    assert error["correlation_id"]
