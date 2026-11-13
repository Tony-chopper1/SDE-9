
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.schemas.events import EventCreate
from backend.services.event_service import event_service
from backend.api.sessions import session_service


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Events"],
)


@router.post(
    "/{session_id}/events",
    status_code=status.HTTP_201_CREATED,
)
async def publish_event(
    session_id: UUID,
    data: EventCreate,
):
    session = session_service.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    return await event_service.publish_event(session_id, data)


@router.get("/{session_id}/events")
async def stream_events(session_id: UUID):
    session = session_service.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    async def event_generator():
        async for event in event_service.stream_events(session_id):
            event_data = json.dumps(
                event.model_dump(mode="json"),
                ensure_ascii=False,
            )

            yield (
                f"id: {event.event_id}\n"
                f"event: {event.event_type}\n"
                f"data: {event_data}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
