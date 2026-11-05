"""
Audio source interfaces and deterministic mock microphone implementation.
Owner: Satwik A (feature/audio-vad)

Provides:
- AudioSource: Abstract base class for capture devices / stream sources.
- MockMicrophoneSource: Hardware-free, deterministic 16-bit PCM waveform generator.
- MockMicSource: Backward-compatible alias for MockMicrophoneSource.

End-of-stream behavior:
- read_frame() returns None when the stream finishes or reaches its configured duration.
- stream() terminates cleanly without emitting sentinel empty frames.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import math
import struct
import time
from typing import Iterator, List, Optional, Tuple
import uuid

from packages.audio.exceptions import AudioSourceError
from packages.audio.models import AudioConfig, AudioFrame


class AudioSource(ABC):
    """Abstract base class for an audio capture device or stream source."""

    @abstractmethod
    def open(self) -> None:
        """Initialize and open the audio source stream."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the audio source stream and release resources."""
        pass

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Return True if the audio source is currently open and producing frames."""
        pass

    @abstractmethod
    def read_frame(self) -> Optional[AudioFrame]:
        """Read the next audio frame.

        Returns:
            An AudioFrame instance, or None if end-of-stream is reached.
        """
        pass

    def __enter__(self) -> AudioSource:
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def stream(self) -> Iterator[AudioFrame]:
        """Yield frames until the stream concludes or is closed.

        Cleanly terminates without emitting empty sentinel frames.
        """
        while self.is_active:
            frame = self.read_frame()
            if frame is None:
                break
            yield frame


class MockMicrophoneSource(AudioSource):
    """Deterministic, hardware-independent mock microphone source.

    Synthesizes discrete 16-bit linear PCM (s16le) audio frames without
    physical audio hardware. Supports both 20ms (640 bytes) and 30ms (960 bytes)
    frame windows at 16000 Hz mono.
    """

    SUPPORTED_PATTERNS = {"speech", "silence", "alternating", "custom"}

    def __init__(
        self,
        config: Optional[AudioConfig] = None,
        pattern: str = "alternating",
        custom_timeline: Optional[List[Tuple[str, int]]] = None,
        duration_seconds: Optional[float] = None,
        max_frames: Optional[int] = None,
        real_time: bool = False,
        speech_frequency_hz: float = 300.0,
    ):
        """Initialize the mock microphone.

        Args:
            config: Audio stream configuration (defaults to 16kHz, mono, s16le, 30ms).
            pattern: Pattern style: 'speech', 'silence', 'alternating', or 'custom'.
            custom_timeline: For 'custom' pattern, list of (segment_type, duration_ms) tuples.
            duration_seconds: Max stream length in seconds.
            max_frames: Max frame count before EOF.
            real_time: If True, sleeps for frame duration between reads to mimic live mic.
            speech_frequency_hz: Base carrier frequency for synthesized speech tone.
        """
        self.config = config or AudioConfig()
        if pattern not in self.SUPPORTED_PATTERNS:
            raise AudioSourceError(
                f"Unknown mock mic pattern: '{pattern}'. Supported: {sorted(self.SUPPORTED_PATTERNS)}",
                details={"pattern": pattern},
            )
        self.pattern = pattern
        self.custom_timeline = custom_timeline or []
        self.real_time = real_time
        self.speech_frequency_hz = speech_frequency_hz

        if duration_seconds is not None:
            frames_from_duration = int((duration_seconds * 1000) / self.config.frame_duration_ms)
            self.max_frames = frames_from_duration
        else:
            self.max_frames = max_frames

        self._is_open = False
        self.is_streaming = False
        self._sequence_counter = 0
        self._sample_index = 0
        self._last_read_time: Optional[float] = None

    def start_streaming(self) -> None:
        """Team interface: Start streaming audio frames."""
        self.open()

    def stop_streaming(self) -> None:
        """Team interface: Stop streaming audio frames."""
        self.close()

    def open(self) -> None:
        """Open the mock source and reset counters."""
        self._is_open = True
        self.is_streaming = True
        self._sequence_counter = 0
        self._sample_index = 0
        self._last_read_time = time.perf_counter()

    def close(self) -> None:
        """Close the mock source."""
        self._is_open = False
        self.is_streaming = False

    @property
    def is_active(self) -> bool:
        """Whether source is currently open and producing frames."""
        if not self._is_open:
            return False
        if self.max_frames is not None and self._sequence_counter >= self.max_frames:
            return False
        return True

    def _should_generate_speech_at(self, elapsed_ms: float) -> bool:
        """Determine whether current timeline position contains speech or silence."""
        if self.pattern == "speech":
            return True
        elif self.pattern == "silence":
            return False
        elif self.pattern == "alternating":
            # 600ms speech followed by 600ms silence cycle
            cycle_ms = 1200.0
            phase = elapsed_ms % cycle_ms
            return phase < 600.0
        elif self.pattern == "custom":
            if not self.custom_timeline:
                return False
            total_timeline_ms = sum(dur for _, dur in self.custom_timeline)
            if total_timeline_ms == 0:
                return False
            phase = elapsed_ms % total_timeline_ms
            accum = 0.0
            for seg_type, seg_dur in self.custom_timeline:
                accum += seg_dur
                if phase < accum:
                    return seg_type.lower() == "speech"
            return False
        else:
            raise AudioSourceError(f"Unknown mock mic pattern: '{self.pattern}'")

    def _generate_pcm_samples(self, is_speech: bool, sample_count: int) -> bytes:
        """Synthesize 16-bit signed little-endian PCM samples deterministically."""
        samples: List[int] = []
        sr = self.config.sample_rate

        for i in range(sample_count):
            global_idx = self._sample_index + i
            if is_speech:
                # Multi-harmonic vocal tone with natural amplitude envelope
                t = global_idx / sr
                f0 = self.speech_frequency_hz
                amplitude = 18000.0  # Safe within int16 [-32768, 32767]
                modulation = 0.85 + 0.15 * math.sin(2.0 * math.pi * 5.0 * t)
                val = (
                    0.65 * math.sin(2.0 * math.pi * f0 * t)
                    + 0.35 * math.sin(2.0 * math.pi * (2.0 * f0) * t)
                ) * amplitude * modulation
                sample_int = int(max(-32767, min(32767, val)))
            else:
                sample_int = 0

            for _ in range(self.config.channels):
                samples.append(sample_int)

        self._sample_index += sample_count
        return struct.pack(f"<{len(samples)}h", *samples)

    def generate_synthetic_frame(self, is_speech: bool = False) -> AudioFrame:
        """Team interface: Produce a single synthetic AudioFrame (silent or simulated speech).

        Operates whether streaming is active or standalone, advancing the internal counter.
        """
        if not self._is_open:
            self._is_open = True
            self.is_streaming = True

        sample_count = self.config.samples_per_frame
        pcm_bytes = self._generate_pcm_samples(is_speech, sample_count)
        elapsed_ms = float(self._sequence_counter * self.config.frame_duration_ms)

        frame = AudioFrame(
            data=pcm_bytes,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            format=self.config.format,
            frame_duration_ms=self.config.frame_duration_ms,
            frame_index=self._sequence_counter,
            sequence_number=self._sequence_counter,
            timestamp_ms=elapsed_ms,
            is_speech=is_speech,
            frame_id=f"frame-{uuid.uuid4().hex[:10]}",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )
        self._sequence_counter += 1
        return frame

    def read_frame(self) -> Optional[AudioFrame]:
        """Produce the next deterministic audio frame.

        Returns:
            An AudioFrame instance, or None on EOF. Never returns an empty AudioFrame.
        """
        if not self._is_open:
            raise AudioSourceError("Cannot read from closed MockMicrophoneSource. Call open() first.")

        if self.max_frames is not None and self._sequence_counter >= self.max_frames:
            return None

        # Real-time pacing if requested
        if self.real_time and self._last_read_time is not None:
            now = time.perf_counter()
            frame_sec = self.config.frame_duration_ms / 1000.0
            elapsed = now - self._last_read_time
            sleep_needed = frame_sec - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)
            self._last_read_time = time.perf_counter()

        elapsed_ms = float(self._sequence_counter * self.config.frame_duration_ms)
        is_speech = self._should_generate_speech_at(elapsed_ms)
        sample_count = self.config.samples_per_frame
        pcm_bytes = self._generate_pcm_samples(is_speech, sample_count)

        frame = AudioFrame(
            data=pcm_bytes,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            format=self.config.format,
            frame_duration_ms=self.config.frame_duration_ms,
            frame_index=self._sequence_counter,
            sequence_number=self._sequence_counter,
            timestamp_ms=elapsed_ms,
            is_speech=is_speech,
            frame_id=f"frame-{uuid.uuid4().hex[:10]}",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

        self._sequence_counter += 1
        return frame


# Backward-compatible alias
MockMicSource = MockMicrophoneSource

__all__ = [
    "AudioSource",
    "MockMicrophoneSource",
    "MockMicSource",
]
