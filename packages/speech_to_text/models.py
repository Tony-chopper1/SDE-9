"""
Speech-to-Text Data Models & Schemas

Defines core data models for speech segments, accumulated utterances,
and transcript events with strict input validation.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccumulatorState(str, Enum):
    """Lifecycle states of the segment accumulator state machine."""
    IDLE = "IDLE"
    ACCUMULATING = "ACCUMULATING"
    PAUSED = "PAUSED"
    FINALIZED = "FINALIZED"


class TranscriptSegment(BaseModel):
    """
    Represents an atomic transcript chunk received from an STT engine.
    Supports streaming partials (is_final=False) and final commitments (is_final=True).
    """
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique chunk or segment ID")
    text: str = Field(..., description="Recognized speech text")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Confidence score [0.0, 1.0]")
    start_time: float = Field(..., description="Start timestamp in seconds")
    end_time: float = Field(..., description="End timestamp in seconds")
    is_final: bool = Field(default=True, description="Whether segment is committed (final) or interim (partial)")
    is_low_confidence: bool = Field(default=False, description="Flagged true if confidence falls below threshold")
    speaker_id: Optional[str] = None
    language: str = "en"

    @model_validator(mode="after")
    def validate_segment(self) -> "TranscriptSegment":
        """Enforce chronological timestamp validity and non-empty ID."""
        if not self.id or not str(self.id).strip():
            raise ValueError("Segment id cannot be empty.")
        if self.start_time < 0.0:
            raise ValueError(f"start_time cannot be negative: {self.start_time}")
        if self.end_time < 0.0:
            raise ValueError(f"end_time cannot be negative: {self.end_time}")
        if self.end_time < self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) cannot be earlier than start_time ({self.start_time})"
            )
        return self


class AccumulatedUtterance(BaseModel):
    """
    Represents a fully merged, coherent spoken sentence or command synthesized
    from multiple individual transcript segments.
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    session_id: str
    full_text: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    start_time: float
    end_time: float
    duration: float = 0.0
    is_complete: bool = True

    @model_validator(mode="after")
    def validate_utterance(self) -> "AccumulatedUtterance":
        """Compute duration and validate timestamp ordering."""
        if self.end_time < self.start_time:
            raise ValueError("end_time cannot be less than start_time")
        if self.duration <= 0.0:
            self.duration = round(max(0.0, self.end_time - self.start_time), 3)
        return self


class TranscriptEvent(BaseModel):
    """
    Event emitted when a segment is processed, revised, finalized, cancelled,
    or an utterance is finalized.
    Provides standard event envelope for inter-service communication carrying
    its required session_id and optional correlation_id.
    """
    model_config = ConfigDict(extra="ignore")

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event identifier")
    event_type: str = Field(default="transcript.segment", description="Event classification (e.g. transcript.interim, transcript.revised, transcript.final, transcript.utterance, transcript.cancelled, transcript.fallback)")
    session_id: str = Field(..., description="Active session ID associated with this event")
    correlation_id: Optional[str] = Field(default=None, description="Optional distributed tracing correlation ID")
    schema_version: str = Field(default="1.0", description="Contract schema version")
    producer: str = Field(default="speech_to_text", description="Originating service producer")
    segment: Optional[TranscriptSegment] = None
    utterance: Optional[AccumulatedUtterance] = None
    is_fallback: bool = Field(default=False, description="Whether event originated during mock provider fallback")
    details: Optional[dict] = Field(default=None, description="Additional metadata or error context")
    timestamp: float = Field(default_factory=time.time, description="Unix timestamp in seconds")

    @model_validator(mode="after")
    def validate_session_id(self) -> "TranscriptEvent":
        """Ensure session_id is always present and non-empty."""
        if not self.session_id or not str(self.session_id).strip():
            raise ValueError("session_id must be a non-empty string.")
        return self

    def to_backend_payload(self) -> dict:
        """Serialize into backend-compatible EventCreate dictionary payload."""
        payload = {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "is_fallback": self.is_fallback,
        }
        if self.segment:
            payload["segment"] = self.segment.model_dump(mode="json")
        if self.utterance:
            payload["utterance"] = self.utterance.model_dump(mode="json")
        if self.details:
            payload["details"] = self.details
        return {
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "producer": self.producer,
            "payload": payload,
        }
