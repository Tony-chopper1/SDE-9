"""
Compatibility module re-exporting canonical models from packages.audio.models.

Maintains backward compatibility with earlier audio module interfaces.
Canonical definitions reside in packages.audio.models.
"""
from packages.audio.lifecycle import (
    StreamLifecycleController,
    StreamState,
)
from packages.audio.profiler import (
    AudioProfiler,
    LatencyStats,
    MemoryStats,
    ProfileReport,
    profile_audio_pipeline,
)
from packages.audio.events import (
    AudioEventDispatcher,
    AudioEventType,
    AudioSessionPipeline,
)
from packages.audio.stt_bridge import (
    AudioSTTBridge,
    MultiSessionSTTBridge,
)
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
    "AudioEventDispatcher",
    "AudioEventType",
    "AudioFormat",
    "AudioFrame",
    "AudioProfiler",
    "AudioSessionPipeline",
    "AudioSTTBridge",
    "LatencyStats",
    "MemoryStats",
    "MultiSessionSTTBridge",
    "ProfileReport",
    "profile_audio_pipeline",
    "StreamLifecycleController",
    "StreamState",
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
