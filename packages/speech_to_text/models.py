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
    Event emitted when a segment is processed or an utterance is finalized.
    Provides standard event envelope for inter-service communication.
    """
    model_config = ConfigDict(extra="ignore")

    event_type: str = "transcript.segment"
    session_id: str
    segment: Optional[TranscriptSegment] = None
    utterance: Optional[AccumulatedUtterance] = None
    timestamp: float = Field(default_factory=time.time)
