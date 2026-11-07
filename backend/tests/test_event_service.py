
import pytest
from uuid import uuid4
from pydantic import ValidationError

from backend.schemas.events import EventCreate, MAX_EVENT_PAYLOAD_BYTES
from backend.services.event_service import EventService


@pytest.mark.asyncio
async def test_publish_event():
    service = EventService()
    session_id = uuid4()

    event = await service.publish_event(
        session_id,
        EventCreate(
            event_type="test.event",
            producer="backend",
            payload={"message": "Hello SDK-9"},
        ),
    )

    assert event.event_type == "test.event"
    assert event.session_id == session_id
    assert event.payload["message"] == "Hello SDK-9"


@pytest.mark.asyncio
async def test_event_order_is_preserved():
    service = EventService()
    session_id = uuid4()

    first = await service.publish_event(
        session_id,
        EventCreate(event_type="event.first", payload={"number": 1}),
    )

    second = await service.publish_event(
        session_id,
        EventCreate(event_type="event.second", payload={"number": 2}),
    )

    events = service.get_events(session_id)

    assert len(events) == 2
    assert events[0].event_id == first.event_id
    assert events[1].event_id == second.event_id


@pytest.mark.asyncio
async def test_stream_replays_published_events():
    service = EventService()
    session_id = uuid4()

    await service.publish_event(
        session_id,
        EventCreate(event_type="test.event", payload={"message": "Stream test"}),
    )

    stream = service.stream_events(session_id)

    try:
        event = await anext(stream)
        assert event.event_type == "test.event"
        assert event.payload["message"] == "Stream test"
    finally:
        await stream.aclose()


def test_event_payload_size_limit():
    large_payload = {"message": "x" * MAX_EVENT_PAYLOAD_BYTES}

    with pytest.raises(ValidationError):
        EventCreate(
            event_type="test.event",
            payload=large_payload,
        )


def test_invalid_event_type():
    with pytest.raises(ValidationError):
        EventCreate(event_type="invalid event type")
