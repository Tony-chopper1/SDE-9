"""
Speech-to-Text and Segment Accumulator
Owner: Pavanchand R M (feature/speech-to-text - Team Lead)
"""
from typing import List, Optional
from pydantic import BaseModel, Field
import time


class TranscriptSegment(BaseModel):
    id: str
    text: str
    confidence: float = 0.95
    start_time: float
    end_time: float
    is_final: bool = True
    speaker_id: Optional[str] = None


class AccumulatedUtterance(BaseModel):
    id: str
    session_id: str
    full_text: str
    segments: List[TranscriptSegment] = Field(default_factory=list)
    start_time: float
    end_time: float
    is_complete: bool = True
