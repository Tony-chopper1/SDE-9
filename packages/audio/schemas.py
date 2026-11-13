"""
Compatibility module re-exporting canonical models from packages.audio.models.

Maintains backward compatibility with earlier audio module interfaces.
Canonical definitions reside in packages.audio.models.
"""
from packages.audio.exceptions import AudioError
from packages.audio.models import (
    SUPPORTED_BIT_DEPTHS,
    SUPPORTED_CHANNELS,
    SUPPORTED_FORMATS,
    SUPPORTED_FRAME_DURATIONS_MS,
    SUPPORTED_SAMPLE_RATES,
    AudioChunk,
    AudioConfig,
    AudioFormat,
    AudioFrame,
    EventEnvelope,
    VADEvent,
    VADResult,
    VADState,
)

__all__ = [
    "AudioChunk",
    "AudioConfig",
    "AudioError",
    "AudioFormat",
    "AudioFrame",
    "VADState",
    "VADEvent",
    "VADResult",
    "EventEnvelope",
    "SUPPORTED_SAMPLE_RATES",
    "SUPPORTED_BIT_DEPTHS",
    "SUPPORTED_CHANNELS",
    "SUPPORTED_FRAME_DURATIONS_MS",
    "SUPPORTED_FORMATS",
]
