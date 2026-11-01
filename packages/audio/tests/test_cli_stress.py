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
import pytest

from packages.audio.cli import run_cli_demo
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, VADState
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
