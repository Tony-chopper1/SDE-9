"""
Audio & Voice Activity Detection (VAD) module for SDK-9.
Owner: Satwik A (feature/audio-vad)

Public Interfaces:
- Models & Schemas: AudioConfig, AudioFrame, VADState, VADEvent, VADResult, EventEnvelope
- Audio Sources: AudioSource, MockMicrophoneSource, MockMicSource
- VAD Detectors: BaseVAD, MockVAD, EnergyVAD, SimpleVADDetector
- Device Management (Week 2, D8-9): AudioDeviceAdapter, MockAudioDeviceAdapter, DeviceInfo, PermissionState
- Lifecycle Management (Week 2, D10-11): StreamLifecycleController, StreamState, StreamLifecycleError, InvalidStateTransitionError
- Bounded Buffer (Week 2, D12-13): BoundedAudioBuffer, BackpressureStrategy, BufferTelemetry, BufferError
- Typed Exceptions: AudioError, AudioConfigError, AudioFrameValidationError, AudioSourceError,
                    VADError, AudioDeviceError, DevicePermissionError, DeviceNotFoundError,
                    StreamLifecycleError, InvalidStateTransitionError, BufferError
"""
from packages.audio.buffer import (
    BackpressureStrategy,
    BoundedAudioBuffer,
    BufferError,
    BufferTelemetry,
)
from packages.audio.device import (
    AudioDeviceAdapter,
    DeviceInfo,
    MockAudioDeviceAdapter,
    PermissionState,
)
from packages.audio.exceptions import (
    AudioConfigError,
    AudioDeviceError,
    AudioError,
    AudioFrameValidationError,
    AudioSourceError,
    DeviceNotFoundError,
    DevicePermissionError,
    VADError,
)
from packages.audio.lifecycle import (
    InvalidStateTransitionError,
    StreamLifecycleController,
    StreamLifecycleError,
    StreamState,
)
from packages.audio.mock_mic import (
    AudioSource,
    MockMicSource,
    MockMicrophoneSource,
)
from packages.audio.models import (
    AudioChunk,
    AudioConfig,
    AudioFormat,
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
    "AudioChunk",
    "AudioConfig",
    "AudioFormat",
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
    # Device management (Week 2 D8-9)
    "PermissionState",
    "DeviceInfo",
    "AudioDeviceAdapter",
    "MockAudioDeviceAdapter",
    # Lifecycle controller (Week 2 D10-11)
    "StreamState",
    "StreamLifecycleController",
    "StreamLifecycleError",
    "InvalidStateTransitionError",
    # Bounded buffer (Week 2 D12-13)
    "BoundedAudioBuffer",
    "BackpressureStrategy",
    "BufferTelemetry",
    "BufferError",
    # Error envelope exceptions
    "AudioError",
    "AudioConfigError",
    "AudioFrameValidationError",
    "AudioSourceError",
    "VADError",
    "AudioDeviceError",
    "DevicePermissionError",
    "DeviceNotFoundError",
]
