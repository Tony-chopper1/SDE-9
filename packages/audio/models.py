"""
Audio and VAD module for SDK-9
Owner: Satwik A (feature/audio-vad)
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import time


class VADState(str, Enum):
    SILENCE = "SILENCE"
    SPEECH_START = "SPEECH_START"
    SPEECH = "SPEECH"
    SPEECH_END = "SPEECH_END"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    bit_depth: int = 16
    channels: int = 1
    frame_duration_ms: int = 30


class AudioFrame(BaseModel):
    data: bytes
    timestamp: float = Field(default_factory=time.time)
    sample_rate: int = 16000
    frame_index: int = 0
    is_speech: bool = False


class VADEvent(BaseModel):
    state: VADState
    timestamp: float = Field(default_factory=time.time)
    energy_level: float
    confidence: float = 0.95
