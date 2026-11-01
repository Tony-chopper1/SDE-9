"""
Compatibility module re-exporting AudioSource and MockMicrophoneSource from packages.audio.mock_mic.

Maintains backward compatibility with earlier audio module interfaces.
Canonical definitions reside in packages.audio.mock_mic.
"""
from packages.audio.mock_mic import (
    AudioSource,
    MockMicSource,
    MockMicrophoneSource,
)

__all__ = [
    "AudioSource",
    "MockMicrophoneSource",
    "MockMicSource",
]
