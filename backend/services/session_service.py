from datetime import datetime, timezone
from uuid import UUID

from backend.schemas.session import (
    SessionData,
    SessionStatus,
)


class SessionService:
    def __init__(self):
        self.sessions: dict[UUID, SessionData] = {}

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
    ) -> SessionData | None:
        session = self.get_session(session_id)

        if session is None:
            return None

        session.status = status
        session.updated_at = datetime.now(timezone.utc)
        return session
