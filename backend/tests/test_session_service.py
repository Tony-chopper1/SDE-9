from uuid import uuid4
from backend.schemas.session import SessionStatus
from backend.services.session_service import SessionService


def test_create_session():
    service = SessionService()

    session = service.create_session("student01")

    assert session.user_id == "student01"
    assert session.status == SessionStatus.CREATED
    assert session.session_id is not None


def test_get_all_sessions():
    service = SessionService()

    service.create_session("student01")
    service.create_session("student02")

    sessions = service.get_all_sessions()

    assert len(sessions) == 2


def test_get_session():
    service = SessionService()

    session = service.create_session("student01")

    result = service.get_session(session.session_id)

    assert result == session


def test_get_session_non_existent():
    service = SessionService()
    result = service.get_session(uuid4())
    assert result is None


def test_update_status():
    service = SessionService()

    session = service.create_session("student01")

    updated_session = service.update_status(
        session.session_id,
        SessionStatus.PAUSED,
    )

    assert updated_session.status == SessionStatus.PAUSED


def test_update_status_non_existent():
    service = SessionService()
    updated_session = service.update_status(uuid4(), SessionStatus.PAUSED)
    assert updated_session is None
