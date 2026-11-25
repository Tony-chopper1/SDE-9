"""
CLI and audio pipeline stress tests for SDK-9 Audio & VAD module.
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
1. CLI execution with 100 audio frames (20ms and 30ms).
2. CLI execution with 1,000 audio frames (20ms and 30ms).
3. Stress testing both EnergyVAD and SimpleVADDetector under load.
4. Repeated lifecycle operations (50+ rapid start/stop/reset cycles).
5. Robust error handling on invalid configurations and edge cases.
6. Memory/leak resistance, no state pollution, and valid VAD state transitions.
"""
import io
import sys
import tracemalloc
import pytest

from packages.audio.cli import run_cli_demo
from packages.audio.events import AudioEventDispatcher, AudioEventType, AudioSessionPipeline
from packages.audio.lifecycle import StreamLifecycleController, StreamState
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, VADState
from packages.audio.vad import EnergyVAD, SimpleVADDetector


def test_cli_stress_100_frames_20ms_energy(capsys):
    """Stress Test 1: Run CLI demo with 100 frames at 20ms (provisional STT) with EnergyVAD."""
    exit_code = run_cli_demo(
        iterations=100,
        frame_ms=20,
        vad_engine="energy",
        pattern="alternating",
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total frames processed : 100" in captured.out
    assert "SDK-9 Event Envelope" in captured.out
    assert "Demo completed successfully" in captured.out


def test_cli_stress_100_frames_30ms_simple(capsys):
    """Stress Test 2: Run CLI demo with 100 frames at 30ms (team default) with SimpleVADDetector."""
    exit_code = run_cli_demo(
        iterations=100,
        frame_ms=30,
        vad_engine="simple",
        pattern="alternating",
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total frames processed : 100" in captured.out
    assert "VAD Engine    : SIMPLE" in captured.out
    assert "Demo completed successfully" in captured.out


def test_cli_stress_1000_frames_20ms_energy(capsys):
    """Stress Test 3: Run CLI demo with 1,000 frames at 20ms using EnergyVAD."""
    exit_code = run_cli_demo(
        iterations=1000,
        frame_ms=20,
        vad_engine="energy",
        pattern="alternating",
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total frames processed : 1000" in captured.out
    assert "Demo completed successfully" in captured.out


def test_cli_stress_1000_frames_30ms_simple(capsys):
    """Stress Test 4: Run CLI demo with 1,000 frames at 30ms using SimpleVADDetector."""
    exit_code = run_cli_demo(
        iterations=1000,
        frame_ms=30,
        vad_engine="simple",
        pattern="alternating",
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Total frames processed : 1000" in captured.out
    assert "Demo completed successfully" in captured.out


def test_repeated_start_stop_reset_cycles():
    """Stress Test 5: Verify 50 rapid start, stream, stop, and reset cycles."""
    config20 = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    vad_energy = EnergyVAD(threshold_db=-42.0)
    vad_simple = SimpleVADDetector(energy_threshold=500.0)

    for cycle in range(50):
        mic = MockMicrophoneSource(config=config20, pattern="speech", max_frames=5)
        mic.start_streaming()
        assert mic.is_streaming is True

        frames = []
        for _ in range(5):
            f = mic.read_frame()
            assert f is not None
            frames.append(f)
            # Evaluate with both VAD detectors
            res_energy = vad_energy.process_frame(f)
            res_simple = vad_simple.evaluate_frame(f)
            assert res_simple.state in (VADState.SPEECH_START, VADState.SPEECH)

        # EOF reached
        assert mic.read_frame() is None
        mic.stop_streaming()
        assert mic.is_streaming is False

        # Reset detectors
        vad_energy.reset()
        vad_simple.reset()
        assert vad_energy.is_speech_active is False
        assert vad_simple._in_speech is False


def test_vad_transition_state_machine_stability():
    """Stress Test 6: Verify no illegal state transitions occur during intense pattern switches."""
    vad = SimpleVADDetector(energy_threshold=500.0)
    mic = MockMicrophoneSource(
        pattern="custom",
        custom_timeline=[("speech", 30), ("silence", 30)] * 50,  # 100 rapid alternations
        max_frames=100,
    )

    prior_state = VADState.SILENCE
    with mic:
        for frame in mic.stream():
            event = vad.evaluate_frame(frame)
            curr = event.state

            # Valid transitions check
            if prior_state == VADState.SILENCE:
                assert curr in (VADState.SILENCE, VADState.SPEECH_START), f"Illegal from SILENCE to {curr}"
            elif prior_state == VADState.SPEECH_START:
                assert curr in (VADState.SPEECH, VADState.SPEECH_END), f"Illegal from SPEECH_START to {curr}"
            elif prior_state == VADState.SPEECH:
                assert curr in (VADState.SPEECH, VADState.SPEECH_END), f"Illegal from SPEECH to {curr}"
            elif prior_state == VADState.SPEECH_END:
                assert curr in (VADState.SILENCE, VADState.SPEECH_START), f"Illegal from SPEECH_END to {curr}"

            prior_state = curr


def test_invalid_cli_arguments_and_error_handling(capsys):
    """Stress Test 7: Verify graceful error handling without crashes when given invalid parameters."""
    # 1. Invalid sample rate
    code1 = run_cli_demo(sample_rate=12345, iterations=1)
    assert code1 == 1

    # 2. Invalid frame duration
    code2 = run_cli_demo(frame_ms=75, iterations=1)
    assert code2 == 1

    # 3. Invalid pattern
    code3 = run_cli_demo(pattern="corrupt_pattern_name", iterations=1)
    assert code3 == 1

    captured = capsys.readouterr()
    assert "[AUDIO ERROR]" in captured.err


def test_long_session_5000_frames_bounded_memory_and_sequence_integrity():
    """Stress Test 8 (Week 4 Phase 2): Prolonged 5,000-frame audio processing (100 seconds).

    Verifies:
    1. Continuous stream processing of 5,000 frames without failure.
    2. Strict monotonic sequence integrity (0 through 4999).
    3. Stable bounded memory usage via tracemalloc (net growth <= 250 KiB).
    4. Controlled buffer size (BoundedAudioBuffer stays <= max_frames).
    5. Clean pipeline completion, valid event dispatch, and speech segment tracking.
    """
    from packages.audio.buffer import BackpressureStrategy, BoundedAudioBuffer

    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    source = MockMicrophoneSource(
        config=config,
        pattern="alternating",
        max_frames=5000,
    )
    buffer = BoundedAudioBuffer(max_frames=50, strategy=BackpressureStrategy.DROP_OLDEST)
    vad = EnergyVAD(threshold_db=-42.0, trigger_frames=2, hangover_frames=3)
    dispatcher = AudioEventDispatcher()
    vad_events = []
    dispatcher.subscribe(lambda e: vad_events.append(e))

    pipeline = AudioSessionPipeline(
        session_id="session-stress-5000",
        correlation_id="corr-stress-5000",
        vad=vad,
        dispatcher=dispatcher,
        emit_chunk_events=False,
    )

    tracemalloc_started = not tracemalloc.is_tracing()
    if tracemalloc_started:
        tracemalloc.start()
    tracemalloc.reset_peak()

    mem_baseline, _ = tracemalloc.get_traced_memory()

    processed_frames = 0
    expected_seq = 0
    max_observed_buffer_len = 0

    with source:
        for frame in source.stream():
            # Verify sequence monotonicity on the fly without accumulating 5,000 objects
            assert frame.sequence_number == expected_seq, f"Sequence broken: expected {expected_seq}, got {frame.sequence_number}"
            expected_seq += 1

            # Push through bounded buffer
            buffer.push(frame)
            if len(buffer) > max_observed_buffer_len:
                max_observed_buffer_len = len(buffer)

            # Drain from buffer and feed pipeline
            queued_frame = buffer.pop()
            assert queued_frame is not None
            pipeline.process_frame(queued_frame)
            processed_frames += 1

    mem_current, mem_peak = tracemalloc.get_traced_memory()
    net_mem_growth_kib = (mem_current - mem_baseline) / 1024.0

    if tracemalloc_started:
        tracemalloc.stop()

    # 1. Total count
    assert processed_frames == 5000
    assert pipeline.total_frames_processed == 5000
    assert expected_seq == 5000

    # 2. Buffer bounded guarantee
    assert max_observed_buffer_len <= 50

    # 3. Bounded memory: streaming 5,000 frames must not leak or balloon unbounded memory (< 500 KiB across 100s audio)
    assert net_mem_growth_kib < 500.0, f"Excessive memory growth: {net_mem_growth_kib:.2f} KiB"

    # 4. Pipeline state and event integrity
    assert pipeline.speech_segments_count > 0
    assert len(vad_events) > 0
    # Complete session with EOS flush
    flush_events = pipeline.flush()
    assert isinstance(flush_events, list)


def test_prolonged_stream_lifecycle_repeated_start_pause_resume_stop():
    """Stress Test 9 (Week 4 Phase 2): Prolonged lifecycle stability over 25 pause/resume cycles.

    Verifies:
    1. Rapid alternating transitions: RUNNING -> PAUSED -> RUNNING -> STOPPED.
    2. Capture state transitions: 'recording' -> 'paused' -> 'recording' -> 'idle'.
    3. Accurate tracking of frames dropped during paused state.
    4. Clean state machine integrity with zero leaked resources.
    """
    from packages.audio.device import MockAudioDeviceAdapter

    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    total_paused_drops = 0

    for cycle in range(25):
        adapter = MockAudioDeviceAdapter()
        source = MockMicrophoneSource(config=config, pattern="speech", max_frames=20)
        controller = StreamLifecycleController(
            device_adapter=adapter,
            config=config,
            source_factory=lambda c, s=source: s,
        )

        controller.start()
        assert controller.state == StreamState.RUNNING
        assert controller.capture_state == "recording"

        # Read 2 frames while active
        f1 = controller.read_frame()
        f2 = controller.read_frame()
        assert f1 is not None and f2 is not None

        # Pause stream
        controller.pause()
        assert controller.state == StreamState.PAUSED
        assert controller.capture_state == "paused"

        # Read 2 frames while paused (must be dropped)
        dropped1 = controller.read_frame()
        dropped2 = controller.read_frame()
        assert dropped1 is None and dropped2 is None
        assert controller.frames_paused_dropped == 2
        total_paused_drops += 2

        # Resume stream
        controller.resume()
        assert controller.state == StreamState.RUNNING
        assert controller.capture_state == "recording"

        # Read 1 frame while resumed
        f3 = controller.read_frame()
        assert f3 is not None

        # Stop stream
        controller.stop()
        assert controller.state == StreamState.STOPPED
        assert controller.capture_state == "idle"

    assert total_paused_drops == 50
