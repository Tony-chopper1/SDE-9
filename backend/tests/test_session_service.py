from backend.services.session_service import SessionService
from backend.schemas.session import SessionStatus


def test_resume_session():
    service = SessionService()
    session = service.create_session("student05")
    service.update_status(session.session_id, SessionStatus.PAUSED)

    resumed = service.resume_session(session.session_id)

    assert resumed.status == SessionStatus.ACTIVE


def test_expire_session():
    service = SessionService()
    session = service.create_session("student06")

    expired = service.expire_session(session.session_id)

    assert expired.status == SessionStatus.EXPIRED


def test_invalid_transition():
    service = SessionService()
    session = service.create_session("student07")

    service.update_status(session.session_id, SessionStatus.COMPLETED)

    try:
        service.resume_session(session.session_id)
        assert False, "Expected invalid transition error"
    except ValueError:
        assert True


def test_idempotent_command():
    service = SessionService()
    session = service.create_session("student08")

    first = service.update_status(
        session.session_id,
        SessionStatus.PAUSED,
        "pause-command-001",
    )

    second = service.update_status(
        session.session_id,
        SessionStatus.PAUSED,
        "pause-command-001",
    )

    assert first.status == SessionStatus.PAUSED
    assert second.status == SessionStatus.PAUSED
