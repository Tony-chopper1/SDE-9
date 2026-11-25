
import json
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Body, status
from fastapi.responses import StreamingResponse

from backend.schemas.events import EventCreate
from backend.services.event_service import event_service
from backend.api.sessions import session_service


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Events"],
)

EVENT_EXAMPLE = {
    "event_id": "123e4567-e89b-12d3-a456-426614174002",
    "event_type": "transcription.completed",
    "schema_version": "1.0",
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "timestamp": "2026-11-25T07:00:00Z",
    "producer": "backend",
    "payload": {
        "message": "Transcription completed",
    },
}

ERROR_EXAMPLE = {
    "success": False,
    "data": None,
    "error": {
        "code": "HTTP_404",
        "message_safe_for_user": "Resource not found",
        "retryable": False,
        "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
        "details_redacted": None,
    },
    "timestamp": 1795590000.0,
}


@router.post(
    "/{session_id}/events",
    status_code=status.HTTP_201_CREATED,
    summary="Publish a session event",
    description="Publishes an event to a session's event history.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "transcription_event": {
                            "summary": "Publish a transcription event",
                            "value": {
                                "event_type": "transcription.completed",
                                "schema_version": "1.0",
                                "producer": "backend",
                                "payload": {
                                    "message": "Transcription completed",
                                },
                            },
                        }
                    }
                }
            }
        }
    },
    responses={
        201: {
            "description": "Event published",
            "content": {
                "application/json": {
                    "example": EVENT_EXAMPLE,
                }
            },
        },
        404: {
            "description": "Session not found",
            "content": {
                "application/json": {
                    "example": ERROR_EXAMPLE,
                }
            },
        },
        422: {
            "description": "Invalid event request",
        },
    },
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


@router.get(
    "/{session_id}/events",
    summary="Stream session events",
    description=(
        "Streams session events using Server-Sent Events (SSE). "
        "Use the Last-Event-ID header to reconnect and replay events "
        "after the specified event."
    ),
    responses={
        200: {
            "description": "Server-Sent Event stream",
            "content": {
                "text/event-stream": {
                    "example": (
                        "id: 123e4567-e89b-12d3-a456-426614174002\n"
                        "event: transcription.completed\n"
                        'data: {"event_id":"123e4567-e89b-12d3-a456-426614174002",'
                        '"event_type":"transcription.completed",'
                        '"schema_version":"1.0",'
                        '"session_id":"123e4567-e89b-12d3-a456-426614174000",'
                        '"producer":"backend",'
                        '"payload":{"message":"Transcription completed"}}\n\n'
                    )
                }
            },
        },
        400: {
            "description": "Invalid or unknown Last-Event-ID",
        },
        404: {
            "description": "Session not found",
            "content": {
                "application/json": {
                    "example": ERROR_EXAMPLE,
                }
            },
        },
    },
)
async def stream_events(
    session_id: UUID,
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
        description="Optional event ID used to resume the stream.",
    ),
):
    session = session_service.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    cursor = None

    if last_event_id:
        try:
            cursor = UUID(last_event_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid Last-Event-ID",
            )

        history = event_service.get_events(session_id)

        if not any(event.event_id == cursor for event in history):
            raise HTTPException(
                status_code=400,
                detail="Unknown Last-Event-ID for this session",
            )

    async def event_generator():
        async for event in event_service.stream_events(
            session_id,
            after_event_id=cursor,
        ):
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
