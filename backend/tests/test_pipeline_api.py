
import base64
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def create_test_session():
    response = client.post(
        "/api/v1/sessions",
        json={},
    )
    assert response.status_code == 201
    return response.json()["session_id"]


def test_pipeline_processes_audio_successfully(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={"session_id": session_id},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["data"]["session_id"] == session_id
    assert body["data"]["mock_mode"] is True
    assert body["data"]["audio"]["speech_detected"] is True
    assert body["data"]["transcription"]["text"]
    assert body["data"]["reasoning"]["intent"]


def test_pipeline_accepts_base64_audio(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    session_id = create_test_session()
    audio = b"\x01" * 6400
    encoded_audio = base64.b64encode(audio).decode("ascii")

    response = client.post(
        "/api/v1/pipeline/process",
        json={
            "session_id": session_id,
            "audio_base64": encoded_audio,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["audio"]["received_bytes"] == 6400


def test_pipeline_rejects_invalid_base64(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={
            "session_id": session_id,
            "audio_base64": "not-valid-base64!!!",
        },
    )

    assert response.status_code == 400


def test_pipeline_rejects_empty_audio(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={
            "session_id": session_id,
            "audio_base64": "",
        },
    )

    assert response.status_code == 400


def test_pipeline_rejects_unknown_session(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)

    response = client.post(
        "/api/v1/pipeline/process",
        json={"session_id": str(uuid4())},
    )

    assert response.status_code == 404


def test_pipeline_rejects_missing_api_key(monkeypatch):
    monkeypatch.setenv("PIPELINE_API_KEY", "sdk9-test-secret")
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={"session_id": session_id},
    )

    assert response.status_code == 401
    assert response.json()["success"] is False
    assert response.json()["error"]["code"] == "HTTP_401"


def test_pipeline_rejects_incorrect_api_key(monkeypatch):
    monkeypatch.setenv("PIPELINE_API_KEY", "sdk9-test-secret")
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={"session_id": session_id},
        headers={"X-API-Key": "wrong-key"},
    )

    assert response.status_code == 401


def test_pipeline_accepts_correct_api_key(monkeypatch):
    monkeypatch.setenv("PIPELINE_API_KEY", "sdk9-test-secret")
    session_id = create_test_session()

    response = client.post(
        "/api/v1/pipeline/process",
        json={"session_id": session_id},
        headers={"X-API-Key": "sdk9-test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_pipeline_rate_limit(monkeypatch):
    monkeypatch.delenv("PIPELINE_API_KEY", raising=False)

    old_limit = app.state.rate_limit_max
    app.state.rate_limit_max = 1
    app.state.rate_limit_requests.clear()

    try:
        session_id = create_test_session()
        payload = {"session_id": session_id}

        first_response = client.post(
            "/api/v1/pipeline/process",
            json=payload,
        )

        second_response = client.post(
            "/api/v1/pipeline/process",
            json=payload,
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert second_response.json()["success"] is False
        assert (
            second_response.json()["error"]["code"]
            == "RATE_LIMIT_EXCEEDED"
        )
        assert "Retry-After" in second_response.headers

    finally:
        app.state.rate_limit_max = old_limit
        app.state.rate_limit_requests.clear()
