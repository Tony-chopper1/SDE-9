"""
Speech-to-Text Data Models & Schemas
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import time


class AccumulatorState(str, Enum):
    IDLE = "IDLE"
    ACCUMULATING = "ACCUMULATING"
    PAUSED = "PAUSED"
    FINALIZED = "FINALIZED"


class TranscriptSegment(BaseModel):
    """
    Represents an atomic transcript chunk received from an STT engine.
    Supports streaming partials (is_final=False) and final commitments (is_final=True).
    """
    id: str
    text: str
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    start_time: float = Field(..., description="Start timestamp in seconds")
    end_time: float = Field(..., description="End timestamp in seconds")
    is_final: bool = True
    speaker_id: Optional[str] = None
    language: str = "en"


class AccumulatedUtterance(BaseModel):
    """
    Represents a fully merged, coherent spoken sentence or command.
    """
    id: str
    session_id: str
    full_text: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    start_time: float
    end_time: float
    duration: float = 0.0
    is_complete: bool = True


class TranscriptEvent(BaseModel):
    """
    Event emitted when a segment is processed or an utterance is finalized.
    """
    event_type: str = "transcript.segment"
    session_id: str
    segment: Optional[TranscriptSegment] = None
    utterance: Optional[AccumulatedUtterance] = None
    timestamp: float = Field(default_factory=time.time)
