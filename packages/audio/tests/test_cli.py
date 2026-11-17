"""
Unit tests for Audio & VAD CLI tool and public exports.
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
- Public package exports in packages.audio
- ASCII volume meter rendering
- Default demo execution with run_cli_demo(iterations=10)
- Interactive CLI executions (energy, simple, mock engines)
- Provisional STT 20ms frame support in CLI
- Error handling on invalid parameters
- main() argument parsing and exit codes
"""
import pytest
import sys

import packages.audio as audio_pkg
from packages.audio.cli import main, render_audio_meter, run_cli_demo


def test_public_package_exports():
    """Verify packages.audio exports all agreed team and extended interfaces."""
    # Team interfaces
    assert hasattr(audio_pkg, "AudioConfig")
    assert hasattr(audio_pkg, "AudioFrame")
    assert hasattr(audio_pkg, "VADEvent")
    assert hasattr(audio_pkg, "VADState")
    assert hasattr(audio_pkg, "MockMicrophoneSource")
    assert hasattr(audio_pkg, "SimpleVADDetector")

    # Extended interfaces
    assert hasattr(audio_pkg, "BaseVAD")
    assert hasattr(audio_pkg, "MockVAD")
    assert hasattr(audio_pkg, "EnergyVAD")
    assert hasattr(audio_pkg, "AudioSource")
    assert hasattr(audio_pkg, "MockMicSource")
    assert hasattr(audio_pkg, "VADResult")
    assert hasattr(audio_pkg, "EventEnvelope")

    # Exceptions
    assert hasattr(audio_pkg, "AudioError")
    assert hasattr(audio_pkg, "AudioConfigError")
    assert hasattr(audio_pkg, "AudioFrameValidationError")
    assert hasattr(audio_pkg, "AudioSourceError")
    assert hasattr(audio_pkg, "VADError")


def test_render_audio_meter():
    """Verify ASCII meter rendering logic."""
    meter_silent = render_audio_meter(-100.0, width=10)
    assert meter_silent == "[          ]"

    meter_loud = render_audio_meter(0.0, width=10)
    assert meter_loud == "[==========]"

    meter_mid = render_audio_meter(-30.0, width=10)
    assert len(meter_mid) == 12  # brackets + 10 chars
    assert "=" in meter_mid


def test_run_cli_demo_default_team_signature(capsys):
    """Verify run_cli_demo(iterations=10) default execution works cleanly."""
    exit_code = run_cli_demo(iterations=10)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "SDK-9 AI Voice Co-Pilot -- Audio Pipeline & VAD CLI Demo" in captured.out
    assert "Total frames processed : 10" in captured.out
    assert "SDK-9 Event Envelope" in captured.out


def test_run_cli_demo_with_simple_vad_engine(capsys):
    """Verify CLI works with the team SimpleVADDetector engine."""
    exit_code = run_cli_demo(
        iterations=5,
        vad_engine="simple",
        threshold=500.0,
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "VAD Engine    : SIMPLE" in captured.out
    assert "Total frames processed : 5" in captured.out


def test_run_cli_demo_with_mock_vad_engine():
    """Verify CLI works with the deterministic MockVAD engine."""
    exit_code = run_cli_demo(
        iterations=5,
        vad_engine="mock",
    )
    assert exit_code == 0


def test_run_cli_demo_with_20ms_frames():
    """Verify CLI works with provisional STT 20ms frames (640 bytes)."""
    exit_code = run_cli_demo(
        duration_seconds=0.1,  # 0.1s / 20ms = 5 frames
        frame_ms=20,
        vad_engine="energy",
    )
    assert exit_code == 0


def test_run_cli_demo_invalid_config(capsys):
    """Verify graceful handling and exit code 1 when given invalid configuration."""
    exit_code = run_cli_demo(
        sample_rate=99999,  # Unsupported sample rate
        iterations=2,
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "[AUDIO ERROR]" in captured.err


def test_cli_main_entrypoint(monkeypatch):
    """Verify main() argument parsing and exit handling."""
    test_args = [
        "packages/audio/cli.py",
        "--pattern", "silence",
        "--iterations", "3",
        "--frame-ms", "30",
        "--vad-engine", "energy",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
