"""
Audio & VAD profiling utility for high-resolution latency and memory measurements.
Owner: Satwik A (features/Satwik-week4) - Week 4 (Days 22-24)

Provides:
- LatencyStats: Dataclass holding min, mean, median/p50, p95, and max latency in milliseconds.
- MemoryStats: Dataclass holding baseline, peak, and net memory delta in KiB.
- ProfileReport: Comprehensive profiling summary with structured formatting.
- AudioProfiler: Non-intrusive profiler capturing per-frame latency via time.perf_counter_ns()
  and heap allocation via tracemalloc.
- profile_audio_pipeline: Reproducible programmatic and CLI-accessible benchmark runner.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import statistics
import time
import tracemalloc
from typing import Any, Dict, List

from packages.audio.events import AudioSessionPipeline
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig
from packages.audio.vad import EnergyVAD


def _compute_percentile(sorted_values: List[float], p: float) -> float:
    """Compute the p-th percentile (0.0 to 1.0) using nearest-rank method."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = int(math.ceil(p * len(sorted_values))) - 1
    clamped_rank = max(0, min(len(sorted_values) - 1, rank))
    return sorted_values[clamped_rank]


@dataclass(frozen=True)
class LatencyStats:
    """Summary latency statistics for discrete audio processing operations."""
    count: int = 0
    min_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0
    total_duration_ms: float = 0.0

    @classmethod
    def from_durations_ns(cls, durations_ns: List[int]) -> LatencyStats:
        """Construct LatencyStats from a list of duration measurements in nanoseconds."""
        if not durations_ns:
            return cls()
        # Convert nanoseconds to milliseconds
        ms_vals = [ns / 1_000_000.0 for ns in durations_ns]
        sorted_ms = sorted(ms_vals)
        n = len(sorted_ms)
        min_v = sorted_ms[0]
        max_v = sorted_ms[-1]
        mean_v = statistics.mean(sorted_ms)
        median_v = statistics.median(sorted_ms)
        p95_v = _compute_percentile(sorted_ms, 0.95)
        total_v = sum(sorted_ms)

        return cls(
            count=n,
            min_ms=round(min_v, 4),
            mean_ms=round(mean_v, 4),
            median_ms=round(median_v, 4),
            p95_ms=round(p95_v, 4),
            max_ms=round(max_v, 4),
            total_duration_ms=round(total_v, 4),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize statistics to a clean dictionary."""
        return {
            "count": self.count,
            "min_ms": self.min_ms,
            "mean_ms": self.mean_ms,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
            "max_ms": self.max_ms,
            "total_duration_ms": self.total_duration_ms,
        }


@dataclass(frozen=True)
class MemoryStats:
    """Heap memory usage statistics captured via tracemalloc."""
    baseline_kib: float = 0.0
    current_kib: float = 0.0
    peak_kib: float = 0.0
    delta_kib: float = 0.0

    @classmethod
    def from_tracemalloc(
        cls,
        baseline_bytes: int,
        current_bytes: int,
        peak_bytes: int,
    ) -> MemoryStats:
        """Construct MemoryStats from raw byte measurements."""
        base_kib = baseline_bytes / 1024.0
        curr_kib = current_bytes / 1024.0
        peak_kib = peak_bytes / 1024.0
        delta_kib = (current_bytes - baseline_bytes) / 1024.0
        return cls(
            baseline_kib=round(base_kib, 2),
            current_kib=round(curr_kib, 2),
            peak_kib=round(peak_kib, 2),
            delta_kib=round(delta_kib, 2),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memory statistics to dictionary."""
        return {
            "baseline_kib": self.baseline_kib,
            "current_kib": self.current_kib,
            "peak_kib": self.peak_kib,
            "delta_kib": self.delta_kib,
        }


@dataclass
class ProfileReport:
    """Consolidated audio profiling report holding latency, memory, and throughput metrics."""
    frames_processed: int
    audio_duration_ms: float
    wall_clock_s: float
    vad_latency: LatencyStats
    pipeline_latency: LatencyStats
    memory: MemoryStats

    @property
    def realtime_factor(self) -> float:
        """Ratio of audio duration to wall-clock processing time (> 1.0 means faster than real-time)."""
        wall_ms = self.wall_clock_s * 1000.0
        if wall_ms <= 0:
            return 0.0
        return round(self.audio_duration_ms / wall_ms, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize report to dictionary."""
        return {
            "frames_processed": self.frames_processed,
            "audio_duration_ms": self.audio_duration_ms,
            "wall_clock_s": round(self.wall_clock_s, 4),
            "realtime_factor": self.realtime_factor,
            "vad_latency_ms": self.vad_latency.to_dict(),
            "pipeline_latency_ms": self.pipeline_latency.to_dict(),
            "memory_kib": self.memory.to_dict(),
        }

    def format_table(self) -> str:
        """Render a readable terminal summary table."""
        lines = [
            "=" * 76,
            "  SDK-9 Audio & VAD Profiling Report (Week 4 Days 22-24)",
            "=" * 76,
            f"  Frames Processed    : {self.frames_processed} frames ({self.audio_duration_ms:.0f} ms synthetic audio)",
            f"  Wall-Clock Duration : {self.wall_clock_s:.4f} s",
            f"  Real-Time Speedup   : {self.realtime_factor:.1f}x real-time",
            "-" * 76,
            "  Operation Latency (ms):",
            "  Metric                 Min (ms)   Mean (ms)  p50 (ms)   p95 (ms)   Max (ms)",
            "  ----------------------------------------------------------------------------",
            f"  VAD Evaluation       : {self.vad_latency.min_ms:8.4f}   {self.vad_latency.mean_ms:8.4f}  "
            f"{self.vad_latency.median_ms:8.4f}   {self.vad_latency.p95_ms:8.4f}   {self.vad_latency.max_ms:8.4f}",
            f"  Pipeline Processing  : {self.pipeline_latency.min_ms:8.4f}   {self.pipeline_latency.mean_ms:8.4f}  "
            f"{self.pipeline_latency.median_ms:8.4f}   {self.pipeline_latency.p95_ms:8.4f}   {self.pipeline_latency.max_ms:8.4f}",
            "-" * 76,
            "  Memory Footprint (tracemalloc):",
            f"  Baseline Heap       : {self.memory.baseline_kib:10.2f} KiB",
            f"  Current Heap        : {self.memory.current_kib:10.2f} KiB",
            f"  Peak Heap           : {self.memory.peak_kib:10.2f} KiB",
            f"  Net Heap Delta      : {self.memory.delta_kib:10.2f} KiB",
            "=" * 76,
        ]
        return "\n".join(lines)


class AudioProfiler:
    """High-resolution latency and memory profiler for audio processing operations."""

    def __init__(self, track_memory: bool = True) -> None:
        self.track_memory = track_memory
        self._vad_durations_ns: List[int] = []
        self._pipeline_durations_ns: List[int] = []
        self._start_time: float = 0.0
        self._we_started_tracing: bool = False
        self._baseline_bytes: int = 0
        self._current_bytes: int = 0
        self._peak_bytes: int = 0
        self._frames_count: int = 0
        self._audio_duration_ms: float = 0.0

    def start(self) -> None:
        """Start profiling timer and memory tracking."""
        if self.track_memory:
            if not tracemalloc.is_tracing():
                tracemalloc.start()
                self._we_started_tracing = True
            else:
                self._we_started_tracing = False
            tracemalloc.reset_peak()
            self._baseline_bytes = tracemalloc.get_traced_memory()[0]
        self._start_time = time.perf_counter()

    def record_vad(self, duration_ns: int) -> None:
        """Record discrete VAD operation duration in nanoseconds."""
        self._vad_durations_ns.append(duration_ns)

    def record_pipeline(self, duration_ns: int) -> None:
        """Record discrete pipeline operation duration in nanoseconds."""
        self._pipeline_durations_ns.append(duration_ns)

    def stop(self, frames_processed: int, frame_duration_ms: float) -> ProfileReport:
        """Stop profiling and generate consolidated ProfileReport."""
        wall_clock = time.perf_counter() - self._start_time
        self._frames_count = frames_processed
        self._audio_duration_ms = frames_processed * frame_duration_ms

        if self.track_memory and tracemalloc.is_tracing():
            self._current_bytes, self._peak_bytes = tracemalloc.get_traced_memory()
            mem_stats = MemoryStats.from_tracemalloc(
                baseline_bytes=self._baseline_bytes,
                current_bytes=self._current_bytes,
                peak_bytes=self._peak_bytes,
            )
            if self._we_started_tracing:
                tracemalloc.stop()
        else:
            mem_stats = MemoryStats()

        vad_stats = LatencyStats.from_durations_ns(self._vad_durations_ns)
        pipe_stats = LatencyStats.from_durations_ns(self._pipeline_durations_ns)

        return ProfileReport(
            frames_processed=self._frames_count,
            audio_duration_ms=self._audio_duration_ms,
            wall_clock_s=wall_clock,
            vad_latency=vad_stats,
            pipeline_latency=pipe_stats,
            memory=mem_stats,
        )


def profile_audio_pipeline(
    iterations: int = 200,
    frame_ms: int = 20,
    sample_rate: int = 16000,
    pattern: str = "alternating",
    track_memory: bool = True,
) -> ProfileReport:
    """Execute a reproducible profiling run over MockMicrophoneSource, EnergyVAD, and AudioSessionPipeline.

    Args:
        iterations: Number of audio frames to synthesize and process.
        frame_ms: Frame duration in ms (20 or 30).
        sample_rate: Sampling frequency in Hz.
        pattern: Mock audio synthesis pattern ('alternating', 'speech', 'silence').
        track_memory: Whether to profile heap allocations with tracemalloc.

    Returns:
        Consolidated ProfileReport with latency and memory statistics.
    """
    config = AudioConfig(sample_rate=sample_rate, frame_duration_ms=frame_ms)
    mic = MockMicrophoneSource(
        config=config,
        pattern=pattern,
        max_frames=iterations,
    )
    standalone_vad = EnergyVAD(threshold_db=-42.0)
    pipeline_vad = EnergyVAD(threshold_db=-42.0)
    pipeline = AudioSessionPipeline(session_id="profile-session-001", vad=pipeline_vad)
    profiler = AudioProfiler(track_memory=track_memory)

    profiler.start()
    with mic:
        for frame in mic.stream():
            # 1. Profile discrete VAD evaluation on isolated detector
            t0 = time.perf_counter_ns()
            standalone_vad.process_frame(frame)
            t1 = time.perf_counter_ns()
            profiler.record_vad(t1 - t0)

            # 2. Profile session pipeline chunk processing
            t2 = time.perf_counter_ns()
            pipeline.process_frame(frame)
            t3 = time.perf_counter_ns()
            profiler.record_pipeline(t3 - t2)

    report = profiler.stop(frames_processed=iterations, frame_duration_ms=float(frame_ms))
    return report
