"""
CLI Demonstration Tool for SDK-9 Audio Pipeline, VAD, Lifecycle, and Buffer (Week 2).
Owner: Satwik A (feature/audio-vad)

Usage:
    python packages/audio/cli.py --help
    python packages/audio/cli.py --pattern alternating --duration 1.5
    python packages/audio/cli.py --device mock-usb-headset --buffer-size 10 --buffer-strategy DROP_OLDEST
    python packages/audio/cli.py --demo-lifecycle
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

from packages.audio.buffer import (
    BackpressureStrategy,
    BoundedAudioBuffer,
)
from packages.audio.device import (
    MockAudioDeviceAdapter,
    PermissionState,
)
from packages.audio.exceptions import AudioError
from packages.audio.lifecycle import (
    StreamLifecycleController,
)
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, EventEnvelope, VADState
from packages.audio.vad import BaseVAD, EnergyVAD, MockVAD, SimpleVADDetector


def render_audio_meter(dbfs: float, width: int = 16) -> str:
    """Render a visual ASCII volume meter bar for terminal output."""
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
    min_speech_duration_ms: float = 0.0,
    device_id: Optional[str] = None,
    permission: str = "GRANTED",
    buffer_size: int = 10,
    buffer_strategy: str = "DROP_OLDEST",
    demo_lifecycle: bool = False,
) -> int:
    """Run the complete Week 2 Audio, Device, Lifecycle, VAD & Buffer CLI demo."""
    # Resolve threshold
    if threshold is None:
        if vad_engine == "simple":
            resolved_threshold = 500.0
        elif vad_engine == "mock":
            resolved_threshold = -45.0
        else:
            resolved_threshold = -42.0
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

    print("=" * 76)
    print("  SDK-9 AI Voice Co-Pilot -- Audio Pipeline & VAD CLI Demo (Week 2)")
    print("=" * 76)

    try:
        # 1. Device Discovery & Selection
        perm_enum = PermissionState(permission.upper())
        adapter = MockAudioDeviceAdapter(initial_permission=perm_enum, auto_grant=True)
        print(f"  Permission State: {adapter.get_permission_state().value}")

        available_devices = adapter.list_devices()
        print("  Available Audio Devices:")
        for d in available_devices:
            marker = " (SELECTED)" if (device_id and d.device_id == device_id) or (not device_id and d.is_default) else ""
            print(f"    - [{d.device_id}] {d.name} ({', '.join(str(r) for r in d.sample_rates)} Hz){marker}")

        if device_id:
            adapter.select_device(device_id)

        selected = adapter.get_selected_device()
        print(f"  Active Device   : {selected.name} [{selected.device_id}]")

        config = AudioConfig(
            sample_rate=sample_rate,
            channels=1,
            bit_depth=16,
            format="s16le",
            frame_duration_ms=frame_ms,
        )

        # 2. VAD Engine
        simple_detector: Optional[SimpleVADDetector] = None
        base_detector: Optional[BaseVAD] = None
        unit = "RMS" if vad_engine == "simple" else "dBFS"

        if vad_engine == "simple":
            simple_detector = SimpleVADDetector(
                energy_threshold=resolved_threshold,
                min_speech_duration_ms=min_speech_duration_ms,
            )
        elif vad_engine == "mock":
            base_detector = MockVAD(
                energy_threshold_db=resolved_threshold,
                min_speech_duration_ms=min_speech_duration_ms,
            )
        else:
            base_detector = EnergyVAD(
                threshold_db=resolved_threshold,
                min_speech_duration_ms=min_speech_duration_ms,
            )

        print(f"  VAD Engine    : {vad_engine.upper()} (threshold: {resolved_threshold:.1f} {unit}, min_dur: {min_speech_duration_ms:.0f}ms)")

        # 3. Bounded Buffer Setup
        strat_enum = BackpressureStrategy(buffer_strategy.upper())
        buffer = BoundedAudioBuffer(max_frames=buffer_size, strategy=strat_enum)
        print(f"  Bounded Buffer  : capacity={buffer_size} frames, strategy={strat_enum.value}")
        print(f"  Streaming Mode  : pattern='{pattern}', len={display_len}, realtime={real_time}")
        print("-" * 76)

        # 4. Stream Lifecycle Controller
        controller = StreamLifecycleController(
            device_adapter=adapter,
            config=config,
            source_factory=lambda cfg: MockMicrophoneSource(
                config=cfg,
                pattern=pattern,
                max_frames=max_frames,
                real_time=real_time,
            ),
        )

        controller.start()
        print(f"  Lifecycle State : {controller.state.value}")

        frames_count = 0
        speech_count = 0
        start_time = time.perf_counter()

        print("-" * 76)
        print("  SEQ   TIME_MS   BYTES   RMS        dBFS   METER             VAD STATE     BUF")
        print("-" * 76)

        # Optional lifecycle demonstration: pause and resume mid-stream
        pause_at = max_frames // 3 if demo_lifecycle and max_frames >= 6 else -1

        frame_idx = 0
        while frame_idx < max_frames:
            if demo_lifecycle and frame_idx == pause_at:
                controller.pause()
                print(f"  --- [LIFECYCLE ACTION: PAUSED at index {frame_idx}] ---")
                # Read while paused to demonstrate skipped frames
                for _ in range(2):
                    controller.read_frame()
                print(f"  --- [LIFECYCLE ACTION: RESUMING (skipped {controller.frames_paused_dropped} frames while paused)] ---")
                controller.resume()
                print(f"  --- [LIFECYCLE ACTION: RESUMED at index {frame_idx}] ---")

            frame = controller.read_frame()
            if frame is None:
                break
            frame_idx += 1

            # Push into bounded buffer
            buffer.push(frame)

            # Consume from bounded buffer
            buf_frame = buffer.pop()
            if buf_frame is not None:
                frames_count += 1
                rms = buf_frame.calculate_rms()
                dbfs = buf_frame.calculate_dbfs()
                meter = render_audio_meter(dbfs, width=15)

                if simple_detector is not None:
                    vad_evt = simple_detector.evaluate_frame(buf_frame)
                    is_speech = vad_evt.state in (VADState.SPEECH_START, VADState.SPEECH)
                    state_label = f"[{vad_evt.state.value}]"
                elif base_detector is not None:
                    vad_res = base_detector.process_frame(buf_frame)
                    is_speech = vad_res.is_speech
                    state_label = "[SPEECH]" if is_speech else "[SILENCE]"
                else:
                    is_speech = False
                    state_label = "[UNKNOWN]"

                if is_speech:
                    speech_count += 1

                buf_tele = buffer.get_telemetry()
                buf_stat = f"{buf_tele.current_frames}/{buf_tele.max_frames}"

                print(
                    f"  {buf_frame.frame_index:04d}  {buf_frame.timestamp_ms:6.0f}ms  "
                    f"{len(buf_frame.data):5d}B  {rms:8.1f}  {dbfs:5.1f}  {meter}  {state_label:<12}  {buf_stat}"
                )

        controller.stop()
        buffer.close()
        elapsed = time.perf_counter() - start_time
        speech_pct = (speech_count / frames_count * 100.0) if frames_count else 0.0
        final_tele = buffer.get_telemetry()

        # Construct SDK-9 EventEnvelope summary
        summary_envelope = EventEnvelope.create(
            event_type="audio.vad.summary",
            session_id="session-cli-demo-001",
            payload={
                "frames_processed": frames_count,
                "speech_frames": speech_count,
                "speech_ratio": round(speech_pct / 100.0, 3),
                "vad_engine": vad_engine,
                "device_id": selected.device_id,
                "buffer_capacity": final_tele.max_frames,
                "frames_dropped": final_tele.frames_dropped,
                "bytes_dropped": final_tele.bytes_dropped,
            },
        )

        print("-" * 76)
        print("Pipeline & Buffer Summary:")
        print(f"  Final Lifecycle State  : {controller.state.value}")
        print(f"  Total frames processed : {frames_count}")
        print(f"  Speech frames detected : {speech_count} ({speech_pct:.1f}%)")
        print(f"  Buffer Dropped Frames  : {final_tele.frames_dropped} ({final_tele.bytes_dropped} bytes)")
        print(f"  Wall-clock time        : {elapsed:.2f}s")
        print(f"  SDK-9 Event Envelope   : ID={summary_envelope.event_id}, Version={summary_envelope.schema_version}")
        print("=" * 76)
        print("Demo completed successfully.\n")
        return 0

    except AudioError as err:
        print(f"\n[AUDIO ERROR] Code: {err.code} -- {err.message_safe_for_user}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n[UNEXPECTED ERROR] {exc}", file=sys.stderr)
        return 2


def main() -> None:
    """CLI argument parser and entrypoint."""
    parser = argparse.ArgumentParser(
        description="SDK-9 Audio Pipeline, VAD, Lifecycle & Bounded Buffer offline CLI demonstration."
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
    parser.add_argument(
        "--min-speech-ms",
        type=float,
        default=0.0,
        help="Minimum speech duration in ms required to confirm speech (default: 0.0)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Mock device ID to select (default: system default)",
    )
    parser.add_argument(
        "--permission",
        choices=["GRANTED", "DENIED", "UNAVAILABLE", "PROMPT"],
        default="GRANTED",
        help="Simulate permission state (default: GRANTED)",
    )
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=10,
        help="Bounded buffer capacity in frames (default: 10)",
    )
    parser.add_argument(
        "--buffer-strategy",
        choices=["DROP_OLDEST", "DROP_NEWEST", "BLOCK"],
        default="DROP_OLDEST",
        help="Buffer backpressure strategy (default: DROP_OLDEST)",
    )
    parser.add_argument(
        "--demo-lifecycle",
        action="store_true",
        help="Demonstrate live pause and resume state transitions during streaming",
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
        min_speech_duration_ms=args.min_speech_ms,
        device_id=args.device,
        permission=args.permission,
        buffer_size=args.buffer_size,
        buffer_strategy=args.buffer_strategy,
        demo_lifecycle=args.demo_lifecycle,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
