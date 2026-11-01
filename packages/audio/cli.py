"""
CLI Demonstration Tool for SDK-9 Audio Pipeline & VAD.
Owner: Satwik A (feature/audio-vad)

Usage:
    python packages/audio/cli.py --help
    python packages/audio/cli.py --pattern alternating --duration 2.0
    python packages/audio/cli.py --frame-ms 20 --vad-engine simple
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional

# Ensure repository root is on sys.path when executed directly
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from packages.audio.exceptions import AudioError
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, EventEnvelope, VADState
from packages.audio.vad import BaseVAD, EnergyVAD, MockVAD, SimpleVADDetector


def render_audio_meter(dbfs: float, width: int = 18) -> str:
    """Render a visual ASCII volume meter bar for terminal output.

    Args:
        dbfs: Audio frame decibels relative to full scale (-100.0 dBFS to 0.0 dBFS).
        width: Character width of the meter bar (default: 18).

    Returns:
        Formatted ASCII bar string, e.g. '[==============    ]'.
    """
    clamped = max(-60.0, min(0.0, dbfs))
    ratio = (clamped + 60.0) / 60.0
    filled = int(round(ratio * width))
    bar = "=" * filled + " " * (width - filled)
    return f"[{bar}]"


def run_cli_demo(
    iterations: Optional[int] = 10,
    pattern: str = "alternating",
    duration_seconds: Optional[float] = None,
    sample_rate: int = 16000,
    frame_ms: int = 30,
    real_time: bool = False,
    vad_engine: str = "energy",
    threshold: Optional[float] = None,
) -> int:
    """Run the audio capture and VAD processing loop.

    Preserves team starter signature (iterations: int = 10) while providing
    full interactive options, ASCII meter visualization, and SDK-9 event envelope summary.

    Returns:
        Exit code: 0 on success, 1 on AudioError, 2 on unexpected error.
    """
    # Determine default threshold according to selected engine
    if threshold is None:
        if vad_engine == "simple":
            resolved_threshold = 500.0  # Linear RMS amplitude threshold
        elif vad_engine == "mock":
            resolved_threshold = -45.0  # dBFS threshold
        else:
            resolved_threshold = -42.0  # EnergyVAD dBFS threshold
    else:
        resolved_threshold = threshold

    # Determine max frames
    if duration_seconds is not None:
        max_frames = int((duration_seconds * 1000) / frame_ms)
        display_len = f"{duration_seconds:.1f}s"
    elif iterations is not None:
        max_frames = iterations
        display_len = f"{iterations} frames"
    else:
        max_frames = 10
        display_len = "10 frames"

    print("=" * 72)
    print("  SDK-9 AI Voice Co-Pilot -- Audio Pipeline & VAD CLI Demo")
    print("=" * 72)
    print(f"  Configuration : {sample_rate} Hz, 16-bit Mono PCM, {frame_ms}ms frames")
    print(f"  Mock Source   : pattern='{pattern}', length={display_len}, real_time={real_time}")
    unit = "RMS" if vad_engine == "simple" else "dBFS"
    print(f"  VAD Engine    : {vad_engine.upper()} (threshold: {resolved_threshold:.1f} {unit})")
    print("-" * 72)
    print("  SEQ   TIME_MS   BYTES   RMS        dBFS    METER                 STATE")
    print("-" * 72)

    try:
        config = AudioConfig(
            sample_rate=sample_rate,
            channels=1,
            bit_depth=16,
            format="s16le",
            frame_duration_ms=frame_ms,
        )

        # Initialize requested VAD detector
        simple_detector: Optional[SimpleVADDetector] = None
        base_detector: Optional[BaseVAD] = None

        if vad_engine == "simple":
            simple_detector = SimpleVADDetector(energy_threshold=resolved_threshold)
        elif vad_engine == "mock":
            base_detector = MockVAD(energy_threshold_db=resolved_threshold)
        else:
            base_detector = EnergyVAD(threshold_db=resolved_threshold)

        mic = MockMicrophoneSource(
            config=config,
            pattern=pattern,
            max_frames=max_frames,
            real_time=real_time,
        )

        frames_count = 0
        speech_count = 0
        start_time = time.perf_counter()

        with mic:
            for frame in mic.stream():
                frames_count += 1
                rms = frame.calculate_rms()
                dbfs = frame.calculate_dbfs()
                meter = render_audio_meter(dbfs, width=18)

                if simple_detector is not None:
                    vad_evt = simple_detector.evaluate_frame(frame)
                    is_speech = vad_evt.state in (VADState.SPEECH_START, VADState.SPEECH)
                    state_label = f"[{vad_evt.state.value}]"
                elif base_detector is not None:
                    vad_res = base_detector.process_frame(frame)
                    is_speech = vad_res.is_speech
                    state_label = "[SPEECH]" if is_speech else "[SILENCE]"
                else:
                    is_speech = False
                    state_label = "[UNKNOWN]"

                if is_speech:
                    speech_count += 1

                print(
                    f"  {frame.frame_index:04d}  {frame.timestamp_ms:6.0f}ms  "
                    f"{len(frame.data):5d}B  {rms:8.1f}  {dbfs:6.1f}  {meter}  {state_label:<14}"
                )

        elapsed = time.perf_counter() - start_time
        speech_pct = (speech_count / frames_count * 100.0) if frames_count else 0.0

        # Construct SDK-9 EventEnvelope summary
        summary_envelope = EventEnvelope.create(
            event_type="audio.vad.summary",
            session_id="session-cli-demo-001",
            payload={
                "frames_processed": frames_count,
                "speech_frames": speech_count,
                "speech_ratio": round(speech_pct / 100.0, 3),
                "vad_engine": vad_engine,
                "frame_duration_ms": frame_ms,
                "sample_rate": sample_rate,
            },
        )

        print("-" * 72)
        print("Pipeline Summary:")
        print(f"  Total frames processed : {frames_count}")
        print(f"  Speech frames detected : {speech_count} ({speech_pct:.1f}%)")
        print(f"  Wall-clock time        : {elapsed:.2f}s")
        print(f"  SDK-9 Event Envelope   : ID={summary_envelope.event_id}, Version={summary_envelope.schema_version}")
        print("=" * 72)
        print("Demo completed successfully.\n")
        return 0

    except AudioError as err:
        print(f"\n[AUDIO ERROR] Code: {err.code} — {err.message_safe_for_user}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return 2


def main() -> None:
    """CLI argument parser and entrypoint."""
    parser = argparse.ArgumentParser(
        description="SDK-9 Audio Pipeline & Voice Activity Detection (VAD) offline CLI demonstration."
    )
    parser.add_argument(
        "--pattern",
        choices=["alternating", "speech", "silence"],
        default="alternating",
        help="Synthetic audio pattern to generate (default: alternating)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duration of the audio generation in seconds (e.g. 1.5)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="Number of frames to generate (overrides duration, default: 10)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Audio sample rate in Hz (default: 16000)",
    )
    parser.add_argument(
        "--frame-ms",
        type=int,
        choices=[20, 30],
        default=30,
        help="Frame duration in ms: 30ms (team default) or 20ms (provisional STT) (default: 30)",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Throttle playback to simulate real-time microphone pacing",
    )
    parser.add_argument(
        "--vad-engine",
        choices=["energy", "simple", "mock"],
        default="energy",
        help="VAD engine to use: energy (dBFS), simple (RMS amplitude), mock (default: energy)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Custom VAD threshold (dBFS for energy/mock, RMS amplitude for simple)",
    )

    args = parser.parse_args()
    exit_code = run_cli_demo(
        iterations=args.iterations if args.duration is None and args.iterations is None else args.iterations,
        pattern=args.pattern,
        duration_seconds=args.duration,
        sample_rate=args.sample_rate,
        frame_ms=args.frame_ms,
        real_time=args.realtime,
        vad_engine=args.vad_engine,
        threshold=args.threshold,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
