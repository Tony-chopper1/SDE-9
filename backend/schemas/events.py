
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


MAX_EVENT_PAYLOAD_BYTES = 64 * 1024


class EventCreate(BaseModel):
    event_type: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    schema_version: str = Field(default="1.0", max_length=20)
    producer: str = Field(default="backend", min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, value):
        try:
            size = len(
                json.dumps(value, ensure_ascii=False).encode("utf-8")
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Payload must contain valid JSON data") from exc

        if size > MAX_EVENT_PAYLOAD_BYTES:
            raise ValueError("Event payload exceeds 64 KB")

        return value


class EventRecord(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    schema_version: str
    session_id: UUID
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    producer: str
    payload: dict
