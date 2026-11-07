
from uuid import UUID

from fastapi import APIRouter, HTTPException, Header, status

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


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(data: SessionCreate):
    return session_service.create_session(data.user_id)


@router.get("", response_model=list[SessionResponse])
def get_all_sessions():
    return session_service.get_all_sessions()


@router.get("/{session_id}", response_model=SessionResponse)
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


@router.post("/{session_id}/pause", response_model=SessionResponse)
def pause_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.PAUSED,
        idempotency_key,
    )


@router.post("/{session_id}/resume", response_model=SessionResponse)
def resume_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.ACTIVE,
        idempotency_key,
    )


@router.post("/{session_id}/stop", response_model=SessionResponse)
def stop_session(
    session_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return update_session(
        session_id,
        SessionStatus.COMPLETED,
        idempotency_key,
    )


@router.post("/{session_id}/expire", response_model=SessionResponse)
def expire_session(session_id: UUID):
    session = session_service.expire_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session
