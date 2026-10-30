"""
Audio & VAD Module - Starter Template
Assigned Member: Satwik A (feature/audio-vad - Task W1)
"""
from typing import Optional
from packages.audio.models import AudioConfig, AudioFrame


class MockMicrophoneSource:
    """
    Simulates real audio hardware producing 16kHz 16-bit mono PCM frames.
    
    TODO (Satwik A):
    1. Implement start_streaming and stop_streaming to manage stream state.
    2. Implement generate_synthetic_frame to produce valid PCM audio frames (480 samples for 30ms).
    3. Ensure frames match the AudioFrame schema.
    """
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self.is_streaming = False

    def start_streaming(self) -> None:
        """Start streaming audio frames."""
        raise NotImplementedError("TODO: Satwik A - Implement start_streaming")

    def stop_streaming(self) -> None:
        """Stop streaming audio frames."""
        raise NotImplementedError("TODO: Satwik A - Implement stop_streaming")

    def generate_synthetic_frame(self, is_speech: bool = False) -> AudioFrame:
        """
        Produce a single synthetic AudioFrame (silent or simulated speech).
        """
        raise NotImplementedError("TODO: Satwik A - Implement generate_synthetic_frame")
