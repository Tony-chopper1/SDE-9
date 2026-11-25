
import asyncio
import logging
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.schemas.events import EventCreate
from backend.services.event_service import EventService


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_leak_events():
    service = EventService()
    session_a = uuid4()
    session_b = uuid4()

    event_a = await service.publish_event(
        session_a,
        EventCreate(
            event_type="session.a",
            payload={"message": "only-a"},
        ),
    )
    event_b = await service.publish_event(
        session_b,
        EventCreate(
            event_type="session.b",
            payload={"message": "only-b"},
        ),
    )

    stream_a = service.stream_events(session_a)
    stream_b = service.stream_events(session_b)

    try:
        received_a = await asyncio.wait_for(anext(stream_a), timeout=1)
        received_b = await asyncio.wait_for(anext(stream_b), timeout=1)

        assert received_a.event_id == event_a.event_id
        assert received_b.event_id == event_b.event_id
        assert received_a.session_id == session_a
        assert received_b.session_id == session_b
        assert received_a.payload["message"] == "only-a"
        assert received_b.payload["message"] == "only-b"
    finally:
        await stream_a.aclose()
        await stream_b.aclose()


@pytest.mark.asyncio
async def test_reconnect_replays_only_events_after_last_event_id():
    service = EventService()
    session_id = uuid4()

    first = await service.publish_event(
        session_id,
        EventCreate(event_type="test.first"),
    )
    second = await service.publish_event(
        session_id,
        EventCreate(event_type="test.second"),
    )
    third = await service.publish_event(
        session_id,
        EventCreate(event_type="test.third"),
    )

    stream = service.stream_events(
        session_id,
        after_event_id=first.event_id,
    )

    try:
        replayed_second = await asyncio.wait_for(anext(stream), timeout=1)
        replayed_third = await asyncio.wait_for(anext(stream), timeout=1)

        assert replayed_second.event_id == second.event_id
        assert replayed_third.event_id == third.event_id
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_live_event_arrives_after_reconnect():
    service = EventService()
    session_id = uuid4()

    previous = await service.publish_event(
        session_id,
        EventCreate(event_type="test.previous"),
    )

    stream = service.stream_events(
        session_id,
        after_event_id=previous.event_id,
    )

    try:
        new_event = await service.publish_event(
            session_id,
            EventCreate(
                event_type="test.live",
                payload={"status": "received"},
            ),
        )

        received = await asyncio.wait_for(anext(stream), timeout=1)

        assert received.event_id == new_event.event_id
        assert received.payload["status"] == "received"
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_unknown_reconnect_cursor_is_rejected():
    service = EventService()
    session_id = uuid4()

    stream = service.stream_events(
        session_id,
        after_event_id=uuid4(),
    )

    with pytest.raises(ValueError, match="cursor not found"):
        await anext(stream)

    await stream.aclose()


def test_malformed_json_returns_typed_error_without_traceback():
    client = TestClient(app)

    response = client.post(
        "/api/v1/sessions",
        content=b'{"user_id": "test", invalid',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422

    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["correlation_id"]
    assert "Traceback" not in response.text


def test_request_logs_do_not_expose_sensitive_payload(caplog):
    client = TestClient(app)
    secret_marker = "SDK9_SECRET_LOG_CHECK_12345"

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/api/v1/sessions",
            content=f'{{"user_id": "{secret_marker}", invalid'.encode(),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert secret_marker not in caplog.text
    assert "Traceback" not in caplog.text
