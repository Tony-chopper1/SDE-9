"""
Approved Synthetic Audio Fixtures & Regression Dataset Generators for Speech-to-Text.

Provides deterministic, reproducible, hardware-independent PCM audio streams
for latency benchmarking, CI regression testing, and long-session consistency verification.
"""

from __future__ import annotations

import math
import struct
from typing import Generator, List, Tuple
from pydantic import BaseModel, ConfigDict


class SyntheticAudioChunk(BaseModel):
    """Container for synthetic audio chunk with metadata."""
    model_config = ConfigDict(extra="ignore")

    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    duration_ms: int = 20
    sequence_number: int = 0
    is_speech: bool = True
    intended_text: str = ""


class SyntheticAudioFixtures:
    """Generates approved synthetic audio fixtures for benchmarking and CI regression."""

    @staticmethod
    def generate_pcm_sine(
        frequency_hz: float = 300.0,
        sample_rate: int = 16000,
        duration_ms: int = 20,
        amplitude: float = 0.5,
        channels: int = 1,
    ) -> bytes:
        """Synthesize pure 16-bit linear PCM (s16le) waveform."""
        num_samples = int(sample_rate * (duration_ms / 1000.0))
        max_val = 32767.0 * max(0.0, min(1.0, amplitude))
        raw = bytearray()
        for i in range(num_samples):
            val = int(max_val * math.sin(2.0 * math.pi * frequency_hz * i / sample_rate))
            clamped = max(-32768, min(32767, val))
            sample_bytes = struct.pack("<h", clamped)
            for _ in range(channels):
                raw.extend(sample_bytes)
        return bytes(raw)

    @classmethod
    def clean_speech_stream(
        cls,
        num_frames: int = 50,
        frame_duration_ms: int = 20,
        sample_rate: int = 16000,
    ) -> Generator[SyntheticAudioChunk, None, None]:
        """Generate continuous clean synthetic speech frames."""
        for seq in range(num_frames):
            # Alternating pitch to simulate speech harmonics
            freq = 250.0 + (seq % 5) * 50.0
            data = cls.generate_pcm_sine(
                frequency_hz=freq,
                sample_rate=sample_rate,
                duration_ms=frame_duration_ms,
                amplitude=0.7,
            )
            yield SyntheticAudioChunk(
                data=data,
                sample_rate=sample_rate,
                channels=1,
                duration_ms=frame_duration_ms,
                sequence_number=seq,
                is_speech=True,
                intended_text="clean synthetic speech command",
            )

    @classmethod
    def low_confidence_noise_stream(
        cls,
        num_frames: int = 10,
        frame_duration_ms: int = 20,
    ) -> Generator[SyntheticAudioChunk, None, None]:
        """Generate faint or noisy audio frames that trigger low confidence scores."""
        for seq in range(num_frames):
            data = cls.generate_pcm_sine(
                frequency_hz=80.0,
                duration_ms=frame_duration_ms,
                amplitude=0.03,  # Very low amplitude faint murmur
            )
            yield SyntheticAudioChunk(
                data=data,
                sample_rate=16000,
                channels=1,
                duration_ms=frame_duration_ms,
                sequence_number=seq,
                is_speech=True,
                intended_text="faint murmur",
            )

    @classmethod
    def out_of_order_stream(
        cls,
        total_frames: int = 10,
    ) -> List[SyntheticAudioChunk]:
        """Generate frames with non-monotonic, out-of-order sequence numbers."""
        frames = list(cls.clean_speech_stream(num_frames=total_frames))
        # Scramble sequences: swap pairs (0, 2, 1, 4, 3, etc.)
        for i in range(1, len(frames) - 1, 2):
            frames[i], frames[i + 1] = frames[i + 1], frames[i]
        return frames

    @classmethod
    def sequence_gap_stream(
        cls,
    ) -> List[SyntheticAudioChunk]:
        """Generate frames containing deliberate packet-loss sequence gaps (e.g. 0 -> 5 -> 12)."""
        all_frames = list(cls.clean_speech_stream(num_frames=20))
        # Keep only frame 0, frame 5, frame 12, frame 19
        indices = [0, 5, 12, 19]
        return [all_frames[i] for i in indices]

    @classmethod
    def long_session_stream(
        cls,
        total_frames: int = 300,
    ) -> Generator[SyntheticAudioChunk, None, None]:
        """Generate a simulated multi-minute long session (300+ frames) with speech and pauses."""
        for seq in range(total_frames):
            # Introduce periodic brief silence (every 30 frames)
            is_silence = (seq % 30) in (28, 29)
            if is_silence:
                data = b"\x00" * 640  # 20ms of silence
                yield SyntheticAudioChunk(
                    data=data,
                    duration_ms=20,
                    sequence_number=seq,
                    is_speech=False,
                    intended_text="",
                )
            else:
                data = cls.generate_pcm_sine(
                    frequency_hz=320.0 + (seq % 8) * 30.0,
                    duration_ms=20,
                    amplitude=0.65,
                )
                yield SyntheticAudioChunk(
                    data=data,
                    duration_ms=20,
                    sequence_number=seq,
                    is_speech=True,
                    intended_text=f"utterance segment {seq // 30}",
                )

    @classmethod
    def multi_sample_rate_fixtures(cls) -> List[Tuple[int, int, bytes]]:
        """Generate audio at non-standard rates (8kHz, 44.1kHz, 48kHz, stereo) for preprocessing validation."""
        fixtures = [
            (8000, 1, cls.generate_pcm_sine(300.0, sample_rate=8000, duration_ms=50, channels=1)),
            (44100, 2, cls.generate_pcm_sine(400.0, sample_rate=44100, duration_ms=50, channels=2)),
            (48000, 1, cls.generate_pcm_sine(500.0, sample_rate=48000, duration_ms=50, channels=1)),
        ]
        return fixtures
