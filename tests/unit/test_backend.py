from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"


def test_create_and_get_session():
    create_res = client.post("/api/v1/sessions", json={})
    assert create_res.status_code == 201
    created_session = create_res.json()["data"]
    session_id = created_session["session_id"]

    get_res = client.get(f"/api/v1/sessions/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["session_id"] == session_id


def test_chat_endpoint_validation():
    bad_res = client.post("/api/v1/ai/chat", json={"session_id": "s1", "message": "   "})
    assert bad_res.status_code == 400

    good_res = client.post("/api/v1/ai/chat", json={"session_id": "s1", "message": "Hello Voicebot"})
    assert good_res.status_code == 200
    assert good_res.json()["data"]["status"] == "completed"
