
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class SessionCreate(BaseModel):
    user_id: str | None = None


class SessionResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    created_at: datetime
    updated_at: datetime


class SessionData(BaseModel):
    session_id: UUID = Field(default_factory=uuid4)
    user_id: str | None = None
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
