"""
Unit tests for Audio & VAD profiling utility (Week 4 Days 22-24).
Owner: Satwik A (features/Satwik-week4)

Verifies:
1. LatencyStats summary calculation (min, mean, median/p50, p95, max).
2. MemoryStats calculation from raw byte measurements.
3. AudioProfiler execution and ProfileReport generation.
4. Latency monotonicity and metric validity.
5. ProfileReport formatting and dictionary serialization.
6. Profiler non-intrusiveness (normal audio detection/processing unaltered).
7. CLI demo execution with --profile flag.
"""
from __future__ import annotations

import io
import sys
import pytest

from packages.audio.cli import run_cli_demo
from packages.audio.events import AudioSessionPipeline
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig
from packages.audio.profiler import (
    AudioProfiler,
    LatencyStats,
    MemoryStats,
    ProfileReport,
    profile_audio_pipeline,
)
from packages.audio.vad import EnergyVAD


def test_latency_stats_empty():
    """Verify LatencyStats handles empty inputs safely without error."""
    stats = LatencyStats.from_durations_ns([])
    assert stats.count == 0
    assert stats.min_ms == 0.0
    assert stats.mean_ms == 0.0
    assert stats.median_ms == 0.0
    assert stats.p95_ms == 0.0
    assert stats.max_ms == 0.0
    assert stats.total_duration_ms == 0.0


def test_latency_stats_calculation():
    """Verify LatencyStats correctly computes min, mean, median, p95, and max in milliseconds."""
    # 5 durations: 1ms, 2ms, 3ms, 4ms, 5ms (in nanoseconds)
    durations_ns = [1_000_000, 2_000_000, 3_000_000, 4_000_000, 5_000_000]
    stats = LatencyStats.from_durations_ns(durations_ns)

    assert stats.count == 5
    assert stats.min_ms == 1.0
    assert stats.max_ms == 5.0
    assert stats.mean_ms == 3.0
    assert stats.median_ms == 3.0
    assert stats.p95_ms == 5.0
    assert stats.total_duration_ms == 15.0

    d = stats.to_dict()
    assert d["count"] == 5
    assert d["min_ms"] == 1.0
    assert d["mean_ms"] == 3.0


def test_memory_stats_calculation():
    """Verify MemoryStats converts raw bytes to KiB accurately."""
    stats = MemoryStats.from_tracemalloc(
        baseline_bytes=1024,
        current_bytes=4096,
        peak_bytes=8192,
    )
    assert stats.baseline_kib == 1.0
    assert stats.current_kib == 4.0
    assert stats.peak_kib == 8.0
    assert stats.delta_kib == 3.0

    d = stats.to_dict()
    assert d["baseline_kib"] == 1.0
    assert d["delta_kib"] == 3.0


def test_profile_audio_pipeline_execution():
    """Verify reproducible audio pipeline profiling run generates valid metrics."""
    report = profile_audio_pipeline(iterations=50, frame_ms=20, pattern="alternating")

    assert isinstance(report, ProfileReport)
    assert report.frames_processed == 50
    assert report.audio_duration_ms == 1000.0  # 50 frames * 20ms = 1000ms
    assert report.wall_clock_s > 0.0

    # VAD latency checks
    assert report.vad_latency.count == 50
    assert report.vad_latency.min_ms > 0.0
    assert report.vad_latency.min_ms <= report.vad_latency.mean_ms <= report.vad_latency.max_ms
    assert report.vad_latency.median_ms <= report.vad_latency.p95_ms <= report.vad_latency.max_ms

    # Pipeline latency checks
    assert report.pipeline_latency.count == 50
    assert report.pipeline_latency.min_ms > 0.0
    assert report.pipeline_latency.min_ms <= report.pipeline_latency.mean_ms <= report.pipeline_latency.max_ms

    # Memory checks
    assert report.memory.peak_kib > 0.0

    # Serialization and formatting
    d = report.to_dict()
    assert "vad_latency_ms" in d
    assert "pipeline_latency_ms" in d
    assert "memory_kib" in d
    assert d["frames_processed"] == 50

    table_text = report.format_table()
    assert "SDK-9 Audio & VAD Profiling Report" in table_text
    assert "VAD Evaluation" in table_text
    assert "Pipeline Processing" in table_text
    assert "Memory Footprint" in table_text


def test_profiler_does_not_alter_audio_processing_behavior():
    """Verify profiling does not alter VAD classification counts or results."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    # Run 1: Normal processing without profiler
    mic1 = MockMicrophoneSource(config=config, pattern="alternating", max_frames=30)
    vad1 = EnergyVAD(threshold_db=-42.0)
    pipe1 = AudioSessionPipeline(session_id="unprofiled-sess", vad=vad1)
    speech_count1 = 0
    with mic1:
        for f in mic1.stream():
            v = vad1.process_frame(f)
            if v.is_speech:
                speech_count1 += 1
            pipe1.process_frame(f)

    # Run 2: Processing with AudioProfiler attached
    mic2 = MockMicrophoneSource(config=config, pattern="alternating", max_frames=30)
    vad2 = EnergyVAD(threshold_db=-42.0)
    pipe2 = AudioSessionPipeline(session_id="profiled-sess", vad=vad2)
    profiler = AudioProfiler(track_memory=True)
    profiler.start()
    speech_count2 = 0
    with mic2:
        for f in mic2.stream():
            v = vad2.process_frame(f)
            if v.is_speech:
                speech_count2 += 1
            pipe2.process_frame(f)
    report = profiler.stop(frames_processed=30, frame_duration_ms=20.0)

    assert speech_count1 == speech_count2
    assert report.frames_processed == 30
    assert len(pipe1.dispatcher.history) == len(pipe2.dispatcher.history)


def test_cli_demo_with_profile_flag(capsys):
    """Verify run_cli_demo runs cleanly with profile=True and outputs the profiling table."""
    code = run_cli_demo(iterations=10, profile=True)
    assert code == 0

    captured = capsys.readouterr()
    assert "Demo completed successfully." in captured.out
    assert "SDK-9 Audio & VAD Profiling Report" in captured.out
    assert "VAD Evaluation" in captured.out
    assert "Memory Footprint" in captured.out
