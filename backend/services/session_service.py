
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

from backend.schemas.session import SessionData, SessionStatus


class SessionService:
    def __init__(self):
        self.sessions: dict[UUID, SessionData] = {}
        self.idempotency_records = {}

        self.allowed_transitions = {
            SessionStatus.CREATED: {
                SessionStatus.ACTIVE,
                SessionStatus.PAUSED,
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.EXPIRED,
            },
            SessionStatus.ACTIVE: {
                SessionStatus.PAUSED,
                SessionStatus.STOPPING,
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.EXPIRED,
            },
            SessionStatus.PAUSED: {
                SessionStatus.ACTIVE,
                SessionStatus.STOPPING,
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.EXPIRED,
            },
            SessionStatus.STOPPING: {
                SessionStatus.COMPLETED,
                SessionStatus.FAILED,
                SessionStatus.EXPIRED,
            },
            SessionStatus.COMPLETED: set(),
            SessionStatus.FAILED: set(),
            SessionStatus.EXPIRED: set(),
        }

    def create_session(self, user_id: str | None = None) -> SessionData:
        session = SessionData(user_id=user_id)
        self.sessions[session.session_id] = session
        return session

    def get_all_sessions(self) -> list[SessionData]:
        return list(self.sessions.values())

    def get_session(self, session_id: UUID) -> SessionData | None:
        return self.sessions.get(session_id)

    def update_status(
        self,
        session_id: UUID,
        status: SessionStatus,
        idempotency_key: str | None = None,
    ) -> SessionData | None:
        session = self.get_session(session_id)

        if session is None:
            return None

        if idempotency_key:
            previous = self.idempotency_records.get(idempotency_key)

            if previous:
                previous_session_id, previous_status, result = previous

                if (
                    previous_session_id != session_id
                    or previous_status != status
                ):
                    raise ValueError(
                        "Idempotency key was already used for another command"
                    )

                return deepcopy(result)

        if session.status == status:
            result = deepcopy(session)

            if idempotency_key:
                self.idempotency_records[idempotency_key] = (
                    session_id, status, result
                )

            return result

        if status not in self.allowed_transitions[session.status]:
            raise ValueError(
                f"Invalid session transition: "
                f"{session.status.value} to {status.value}"
            )

        session.status = status
        session.updated_at = datetime.now(timezone.utc)

        if idempotency_key:
            self.idempotency_records[idempotency_key] = (
                session_id, status, deepcopy(session)
            )

        return session

    def resume_session(
        self,
        session_id: UUID,
        idempotency_key: str | None = None,
    ) -> SessionData | None:
        return self.update_status(
            session_id, SessionStatus.ACTIVE, idempotency_key
        )

    def expire_session(self, session_id: UUID) -> SessionData | None:
        return self.update_status(session_id, SessionStatus.EXPIRED)
