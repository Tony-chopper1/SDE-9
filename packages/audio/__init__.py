"""
Audio & Voice Activity Detection (VAD) module for SDK-9.
Owner: Satwik A (feature/audio-vad)

Public Interfaces:
- Models & Schemas: AudioConfig, AudioFrame, VADState, VADEvent, VADResult, EventEnvelope
- Audio Sources: AudioSource, MockMicrophoneSource, MockMicSource
- VAD Detectors: BaseVAD, MockVAD, EnergyVAD, SimpleVADDetector
- Typed Exceptions: AudioError, AudioConfigError, AudioFrameValidationError, AudioSourceError, VADError
"""
from packages.audio.exceptions import (
    AudioConfigError,
    AudioError,
    AudioFrameValidationError,
    AudioSourceError,
    VADError,
)
from packages.audio.mock_mic import (
    AudioSource,
    MockMicSource,
    MockMicrophoneSource,
)
from packages.audio.models import (
    AudioConfig,
    AudioFrame,
    EventEnvelope,
    VADEvent,
    VADResult,
    VADState,
)
from packages.audio.vad import (
    BaseVAD,
    EnergyVAD,
    MockVAD,
    SimpleVADDetector,
)

__all__ = [
    # Team starter interfaces
    "AudioConfig",
    "AudioFrame",
    "VADEvent",
    "VADState",
    "MockMicrophoneSource",
    "SimpleVADDetector",
    # Extended models and shared contracts
    "VADResult",
    "EventEnvelope",
    # Sources and aliases
    "AudioSource",
    "MockMicSource",
    # VAD detector implementations
    "BaseVAD",
    "MockVAD",
    "EnergyVAD",
    # Error envelope exceptions
    "AudioError",
    "AudioConfigError",
    "AudioFrameValidationError",
    "AudioSourceError",
    "VADError",
]
