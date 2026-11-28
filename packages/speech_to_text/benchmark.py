"""
Reproducible Latency Benchmark Harness for Speech-to-Text Module.

Runs automated latency benchmarks against approved synthetic audio fixtures.
Measures:
- Acoustic Preprocessing Latency (Resampling & Peak Normalization)
- Chunk Transcription Latency (p50, p95, p99)
- Reconciler Monotonic Insertion & Deduplication Latency
- End-to-End Audio Frame-to-Transcript Event Latency
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.fixtures import SyntheticAudioFixtures
from packages.speech_to_text.orchestrator import SpeechToTextOrchestrator
from packages.speech_to_text.preprocessor import AudioPreprocessor
from packages.speech_to_text.reconciler import TranscriptReconciler


class BenchmarkMetrics(BaseModel):
    """Statistical summary of latency distribution (all units in milliseconds)."""
    model_config = ConfigDict(extra="ignore")

    count: int
    mean_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float


class LatencyBenchmarkReport(BaseModel):
    """Complete latency benchmark report across all pipeline stages."""
    model_config = ConfigDict(extra="ignore")

    timestamp: float
    iterations: int
    preprocessing_latency: BenchmarkMetrics
    transcription_latency: BenchmarkMetrics
    reconciliation_latency: BenchmarkMetrics
    end_to_end_frame_latency: BenchmarkMetrics
    sla_passed: bool
    details: Dict[str, str] = {}


def calculate_metrics(latencies_ms: List[float]) -> BenchmarkMetrics:
    """Calculate mean, median, p95, p99, min, max from a list of latencies in ms."""
    if not latencies_ms:
        return BenchmarkMetrics(
            count=0, mean_ms=0.0, median_ms=0.0, p95_ms=0.0, p99_ms=0.0, min_ms=0.0, max_ms=0.0
        )
    sorted_l = sorted(latencies_ms)
    n = len(sorted_l)
    p95_idx = min(n - 1, int(n * 0.95))
    p99_idx = min(n - 1, int(n * 0.99))

    return BenchmarkMetrics(
        count=n,
        mean_ms=round(statistics.mean(sorted_l), 3),
        median_ms=round(statistics.median(sorted_l), 3),
        p95_ms=round(sorted_l[p95_idx], 3),
        p99_ms=round(sorted_l[p99_idx], 3),
        min_ms=round(min(sorted_l), 3),
        max_ms=round(max(sorted_l), 3),
    )


def run_latency_benchmark(
    iterations: int = 100,
    warmups: int = 10,
    max_acceptable_e2e_p95_ms: float = 50.0,
) -> LatencyBenchmarkReport:
    """Execute reproducible latency benchmark using approved synthetic audio fixtures.

    Args:
        iterations: Number of benchmark measurement iterations.
        warmups: Warm-up cycles to eliminate JIT/OS startup cache artifacts.
        max_acceptable_e2e_p95_ms: SLA gate threshold for p95 end-to-end frame latency.

    Returns:
        A structured :class:`LatencyBenchmarkReport` with statistical metrics.
    """
    preprocessor = AudioPreprocessor()
    transcriber = FakeTranscriberService()
    reconciler = TranscriptReconciler(session_id="benchmark-session")
    orchestrator = SpeechToTextOrchestrator(session_id="benchmark-orchestrator")
    orchestrator.start()

    # Pre-generate synthetic 20ms and 100ms test frames
    frame_20ms_44k = SyntheticAudioFixtures.generate_pcm_sine(
        frequency_hz=300.0, sample_rate=44100, duration_ms=20, channels=1
    )
    frame_100ms_16k = SyntheticAudioFixtures.generate_pcm_sine(
        frequency_hz=300.0, sample_rate=16000, duration_ms=100, channels=1
    )

    # 1. Warm-up
    for _ in range(warmups):
        preprocessor.process(frame_20ms_44k, source_sample_rate=44100)
        transcriber.transcribe(frame_100ms_16k)
        orchestrator.push_audio(frame_20ms_44k, sample_rate=44100)

    # 2. Benchmark Preprocessor
    prep_latencies: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        preprocessor.process(frame_20ms_44k, source_sample_rate=44100)
        t1 = time.perf_counter()
        prep_latencies.append((t1 - t0) * 1000.0)

    # 3. Benchmark Transcriber
    trans_latencies: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        segments = transcriber.transcribe(frame_100ms_16k)
        t1 = time.perf_counter()
        trans_latencies.append((t1 - t0) * 1000.0)

    # 4. Benchmark Reconciler
    rec_latencies: List[float] = []
    sample_seg = segments[0] if segments else None
    if sample_seg:
        for idx in range(iterations):
            # Unique segment for each iteration
            seg_copy = sample_seg.model_copy(update={"id": f"bench-seg-{idx}", "start_time": idx * 0.1, "end_time": (idx + 1) * 0.1})
            t0 = time.perf_counter()
            reconciler.process_segment(seg_copy)
            t1 = time.perf_counter()
            rec_latencies.append((t1 - t0) * 1000.0)

    # 5. Benchmark End-to-End Orchestrator Ingestion
    e2e_latencies: List[float] = []
    bench_orch = SpeechToTextOrchestrator(session_id="bench-e2e")
    bench_orch.start()
    for seq in range(iterations):
        t0 = time.perf_counter()
        bench_orch.push_audio(frame_20ms_44k, sample_rate=44100, sequence_number=seq)
        t1 = time.perf_counter()
        e2e_latencies.append((t1 - t0) * 1000.0)

    prep_metrics = calculate_metrics(prep_latencies)
    trans_metrics = calculate_metrics(trans_latencies)
    rec_metrics = calculate_metrics(rec_latencies)
    e2e_metrics = calculate_metrics(e2e_latencies)

    sla_passed = e2e_metrics.p95_ms <= max_acceptable_e2e_p95_ms

    return LatencyBenchmarkReport(
        timestamp=time.time(),
        iterations=iterations,
        preprocessing_latency=prep_metrics,
        transcription_latency=trans_metrics,
        reconciliation_latency=rec_metrics,
        end_to_end_frame_latency=e2e_metrics,
        sla_passed=sla_passed,
        details={
            "provider": "FakeTranscriberService (Mock)",
            "resampling": "Linear Interpolation (44.1kHz -> 16kHz)",
            "sla_target_ms": str(max_acceptable_e2e_p95_ms),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SDK-9 Speech-to-Text Latency Benchmark")
    parser.add_argument("--iterations", type=int, default=100, help="Benchmark iterations")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    report = run_latency_benchmark(iterations=args.iterations)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print("\n========================================================")
        print("   SDK-9 Speech-to-Text Latency Benchmark Results")
        print("========================================================")
        print(f"Iterations:        {report.iterations}")
        print(f"SLA Verification:  {'PASSED' if report.sla_passed else 'FAILED'}")
        print("--------------------------------------------------------")
        print(f"Preprocessing (ms):     mean={report.preprocessing_latency.mean_ms:<6} p95={report.preprocessing_latency.p95_ms:<6} p99={report.preprocessing_latency.p99_ms}")
        print(f"Transcription (ms):     mean={report.transcription_latency.mean_ms:<6} p95={report.transcription_latency.p95_ms:<6} p99={report.transcription_latency.p99_ms}")
        print(f"Reconciliation (ms):    mean={report.reconciliation_latency.mean_ms:<6} p95={report.reconciliation_latency.p95_ms:<6} p99={report.reconciliation_latency.p99_ms}")
        print(f"End-to-End Frame (ms):  mean={report.end_to_end_frame_latency.mean_ms:<6} p95={report.end_to_end_frame_latency.p95_ms:<6} p99={report.end_to_end_frame_latency.p99_ms}")
        print("========================================================\n")


if __name__ == "__main__":
    main()
