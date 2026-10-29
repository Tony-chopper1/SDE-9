import math
import struct
import time
from typing import Callable, Optional
from packages.audio.models import AudioConfig, AudioFrame


class MockMicrophoneSource:
    """
    Simulates real audio hardware generating 16kHz 16-bit mono PCM frames.
    """
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        self.is_streaming = False
        self.frame_count = 0

    def start_streaming(self) -> None:
        self.is_streaming = True
        self.frame_count = 0

    def stop_streaming(self) -> None:
        self.is_streaming = False

    def generate_synthetic_frame(self, is_speech: bool = False) -> AudioFrame:
        self.frame_count += 1
        samples_count = int((self.config.sample_rate * self.config.frame_duration_ms) / 1000)

        if is_speech:
            # Generate simulated sine wave for speech audio
            raw_samples = [
                int(math.sin(i / 10.0) * 10000) for i in range(samples_count)
            ]
        else:
            # Silence / ambient low noise
            raw_samples = [0 for _ in range(samples_count)]

        data = struct.pack(f"<{len(raw_samples)}h", *raw_samples)

        return AudioFrame(
            data=data,
            timestamp=time.time(),
            sample_rate=self.config.sample_rate,
            frame_index=self.frame_count,
            is_speech=is_speech,
        )
