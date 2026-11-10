"""
Unit tests for configurable VAD enhancements (Week 2, Days 10-11).
Owner: Satwik A (feature/audio-vad)

Verifies:
- Configurable dBFS energy thresholds (EnergyVAD, MockVAD)
- Configurable minimum speech duration (min_speech_duration_ms)
- Rejection of short impulse clicks below min_speech_duration_ms
- Deterministic detection on synthetic speech and silence fixtures
- Backward compatibility with SimpleVADDetector
"""
import pytest

from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, VADState
from packages.audio.vad import EnergyVAD, MockVAD, SimpleVADDetector


def test_energy_vad_configurable_threshold():
    """Verify speech detection adjusts according to threshold_db."""
    # Create two synthetic frames: one loud (-11 dBFS), one silence (-100 dBFS)
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic_speech = MockMicrophoneSource(config=cfg, pattern="speech", max_frames=5)
    mic_silence = MockMicrophoneSource(config=cfg, pattern="silence", max_frames=5)

    with mic_speech:
        speech_frames = list(mic_speech.stream())
    with mic_silence:
        silence_frames = list(mic_silence.stream())

    # Sensitive detector: -50 dBFS threshold (detects speech easily)
    sensitive_vad = EnergyVAD(threshold_db=-50.0, trigger_frames=1, hangover_frames=0)
    res_speech = sensitive_vad.process_frame(speech_frames[0])
    assert res_speech.is_speech is True
    assert res_speech.energy_db > -50.0

    # Very strict detector: -5.0 dBFS threshold (speech around -11 dBFS should be rejected)
    strict_vad = EnergyVAD(threshold_db=-5.0, trigger_frames=1, hangover_frames=0)
    res_strict = strict_vad.process_frame(speech_frames[0])
    assert res_strict.is_speech is False

    # Silence is rejected by both
    assert sensitive_vad.process_frame(silence_frames[0]).is_speech is False
    assert strict_vad.process_frame(silence_frames[0]).is_speech is False


def test_energy_vad_minimum_speech_duration_filtering():
    """Verify brief audio spikes shorter than min_speech_duration_ms are filtered out."""
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    # Audio timeline: 40ms speech (2 frames) followed by silence.
    # Total active duration is 40ms.
    timeline = [("speech", 40), ("silence", 80)]
    mic = MockMicrophoneSource(config=cfg, pattern="custom", custom_timeline=timeline, max_frames=6)

    with mic:
        frames = list(mic.stream())

    assert len(frames) == 6
    # Frames 0, 1: 20ms each -> total 40ms speech
    # Frames 2..5: silence

    # Case A: VAD requires min 60ms of continuous speech -> 40ms spike must NOT trigger speech!
    vad_filtered = EnergyVAD(
        threshold_db=-40.0,
        trigger_frames=1,
        hangover_frames=0,
        min_speech_duration_ms=60.0,
    )
    results_filtered = [vad_filtered.process_frame(f).is_speech for f in frames]
    assert results_filtered == [False, False, False, False, False, False]

    # Case B: VAD requires min 40ms of continuous speech -> frame 1 (at 40ms) triggers speech!
    vad_accepted = EnergyVAD(
        threshold_db=-40.0,
        trigger_frames=1,
        hangover_frames=0,
        min_speech_duration_ms=40.0,
    )
    results_accepted = [vad_accepted.process_frame(f).is_speech for f in frames]
    # Frame 0 (20ms) is too short -> False; Frame 1 (40ms) reaches threshold -> True
    assert results_accepted[0] is False
    assert results_accepted[1] is True
    # Frames 2..5 are silence -> False
    assert all(r is False for r in results_accepted[2:])


def test_mock_vad_min_speech_duration():
    """Verify MockVAD also supports min_speech_duration_ms parameter."""
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mock_vad = MockVAD(
        scripted_decisions=[True, True, False],
        min_speech_duration_ms=40.0,
    )

    dummy_frame = AudioFrame(
        audio_data=b"\x00" * 640,
        frame_duration_ms=20,
        sample_rate=16000,
    )

    # Frame 1: 20ms -> False (not 40ms yet)
    r1 = mock_vad.process_frame(dummy_frame)
    assert r1.is_speech is False

    # Frame 2: 40ms -> True (meets 40ms requirement)
    r2 = mock_vad.process_frame(dummy_frame)
    assert r2.is_speech is True

    # Frame 3: False -> False
    r3 = mock_vad.process_frame(dummy_frame)
    assert r3.is_speech is False


def test_simple_vad_detector_min_speech_duration():
    """Verify SimpleVADDetector min_speech_duration_ms compatibility."""
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=cfg, pattern="speech", max_frames=3)
    with mic:
        frames = list(mic.stream())

    # Require 40ms
    detector = SimpleVADDetector(energy_threshold=500.0, min_speech_duration_ms=40.0)

    # Frame 0 (20ms): still marked SILENCE because min duration (40ms) not reached
    evt0 = detector.evaluate_frame(frames[0])
    assert evt0.state == VADState.SILENCE

    # Frame 1 (40ms): reaches 40ms, transitions to SPEECH_START
    evt1 = detector.evaluate_frame(frames[1])
    assert evt1.state == VADState.SPEECH_START

    # Frame 2 (60ms): remains in SPEECH
    evt2 = detector.evaluate_frame(frames[2])
    assert evt2.state == VADState.SPEECH
