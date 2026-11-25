
from uuid import UUID

from fastapi import APIRouter, HTTPException, Header, Body, status

from backend.schemas.session import (
    SessionCreate,
    SessionResponse,
    SessionStatus,
)
from backend.services.session_service import SessionService


router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["Sessions"],
)

session_service = SessionService()

SESSION_EXAMPLE = {
    "session_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "created",
    "created_at": "2026-11-25T07:00:00Z",
    "updated_at": "2026-11-25T07:00:00Z",
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

CONFLICT_EXAMPLE = {
    "success": False,
    "data": None,
    "error": {
        "code": "HTTP_409",
        "message_safe_for_user": "Request conflicts with the current resource state",
        "retryable": False,
        "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
        "details_redacted": None,
    },
    "timestamp": 1795590000.0,
}


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a session",
    description="Creates a new voicebot session.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "create_session": {
                            "summary": "Create a session",
                            "value": {"user_id": "demo-user"},
                        }
                    }
                }
            }
        }
    },
    responses={
        201: {
            "description": "Session created successfully",
            "content": {
                "application/json": {
                    "example": SESSION_EXAMPLE,
                }
            },
        },
        422: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "example": ERROR_EXAMPLE,
                }
            },
        },
    },
)
def create_session(data: SessionCreate):
    return session_service.create_session(data.user_id)


@router.get(
    "",
    response_model=list[SessionResponse],
    summary="Get all sessions",
    description="Returns all currently stored sessions.",
    responses={
        200: {
            "description": "List of sessions",
            "content": {
                "application/json": {
                    "example": [SESSION_EXAMPLE],
                }
            },
        },
    },
)
def get_all_sessions():
    return session_service.get_all_sessions()


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get a session",
    description="Returns a session using its session ID.",
    responses={
        200: {
            "description": "Session found",
            "content": {
                "application/json": {
                    "example": SESSION_EXAMPLE,
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
    },
)
def get_session(session_id: UUID):
    session = session_service.get_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


def update_session(
    session_id: UUID,
    target_status: SessionStatus,
    idempotency_key: str | None,
):
    try:
        session = session_service.update_status(
            session_id,
            target_status,
            idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post(
    "/{session_id}/pause",
    response_model=SessionResponse,
    summary="Pause a session",
    description="Pauses an active session. Supports the Idempotency-Key header.",
    responses={
        200: {
            "description": "Session paused",
            "content": {
                "application/json": {
                    "example": {**SESSION_EXAMPLE, "status": "paused"},
                }
            },
        },
        404: {"description": "Session not found", "content": {"application/json": {"example": ERROR_EXAMPLE}}},
        409: {"description": "Invalid session transition", "content": {"application/json": {"example": CONFLICT_EXAMPLE}}},
    },
)
def pause_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.PAUSED,
        idempotency_key,
    )


@router.post(
    "/{session_id}/resume",
    response_model=SessionResponse,
    summary="Resume a session",
    description="Resumes a paused session. Supports the Idempotency-Key header.",
    responses={
        200: {
            "description": "Session resumed",
            "content": {
                "application/json": {
                    "example": {**SESSION_EXAMPLE, "status": "active"},
                }
            },
        },
        404: {"description": "Session not found", "content": {"application/json": {"example": ERROR_EXAMPLE}}},
        409: {"description": "Invalid session transition", "content": {"application/json": {"example": CONFLICT_EXAMPLE}}},
    },
)
def resume_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.ACTIVE,
        idempotency_key,
    )


@router.post(
    "/{session_id}/stop",
    response_model=SessionResponse,
    summary="Stop a session",
    description="Stops a session. Supports the Idempotency-Key header.",
    responses={
        200: {
            "description": "Session stopped",
            "content": {
                "application/json": {
                    "example": {**SESSION_EXAMPLE, "status": "completed"},
                }
            },
        },
        404: {"description": "Session not found", "content": {"application/json": {"example": ERROR_EXAMPLE}}},
        409: {"description": "Invalid session transition", "content": {"application/json": {"example": CONFLICT_EXAMPLE}}},
    },
)
def stop_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.COMPLETED,
        idempotency_key,
    )


@router.post(
    "/{session_id}/expire",
    response_model=SessionResponse,
    summary="Expire a session",
    description="Marks a session as expired.",
    responses={
        200: {
            "description": "Session expired",
            "content": {
                "application/json": {
                    "example": {**SESSION_EXAMPLE, "status": "expired"},
                }
            },
        },
        404: {"description": "Session not found", "content": {"application/json": {"example": ERROR_EXAMPLE}}},
    },
)
def expire_session(session_id: UUID):
    session = session_service.expire_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session
