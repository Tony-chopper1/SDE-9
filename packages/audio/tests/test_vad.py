"""
Unit tests for Voice Activity Detection (BaseVAD, MockVAD, EnergyVAD, SimpleVADDetector).
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
- BaseVAD abstraction
- MockVAD scripted sequence and predictable outputs
- EnergyVAD RMS & dBFS calculation directly from PCM bytes (not frame.is_speech)
- Trigger confirmation frames
- Hangover frames smoothing
- Reset behavior
- SimpleVADDetector transitions (SILENCE, SPEECH_START, SPEECH, SPEECH_END)
- Clear distinction between RMS amplitude thresholds and dBFS thresholds
- Invalid input error handling (raises VADError)
"""
import pytest

from packages.audio.exceptions import VADError
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, VADState
from packages.audio.vad import BaseVAD, EnergyVAD, MockVAD, SimpleVADDetector


def test_base_vad_is_abstract():
    """Verify BaseVAD cannot be instantiated directly without implementations."""
    with pytest.raises(TypeError):
        BaseVAD()  # type: ignore


def test_mock_vad_scripted():
    """Verify MockVAD follows exact scripted boolean sequence."""
    script = [True, False, True, True]
    vad = MockVAD(scripted_decisions=script, default_speech=False)

    dummy_frame = AudioFrame(
        data=b"\x00" * 640,
        frame_duration_ms=20,
    )

    results = [vad.process_frame(dummy_frame).is_speech for _ in range(4)]
    assert results == [True, False, True, True]
    assert vad.frames_processed == 4
    assert vad.speech_frames_detected == 3

    # Subsequent frame falls back to default_speech (False)
    assert vad.process_frame(dummy_frame).is_speech is False
    assert vad.frames_processed == 5


def test_mock_vad_reset():
    """Verify MockVAD reset clears frame count and speech count."""
    vad = MockVAD(scripted_decisions=[True, True])
    frame = AudioFrame(data=b"\x00" * 640, frame_duration_ms=20)
    vad.process_frame(frame)
    assert vad.frames_processed == 1
    assert vad.speech_frames_detected == 1

    vad.reset()
    assert vad.frames_processed == 0
    assert vad.speech_frames_detected == 0


def test_mock_vad_energy_threshold_mode():
    """Verify MockVAD can automatically threshold based on dBFS when not scripted."""
    vad = MockVAD(scripted_decisions=None, energy_threshold_db=-40.0)
    mic = MockMicrophoneSource(max_frames=2)

    silent_frame = mic.generate_synthetic_frame(is_speech=False)
    assert vad.process_frame(silent_frame).is_speech is False

    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    assert vad.process_frame(speech_frame).is_speech is True


def test_vad_invalid_input_error():
    """Verify passing non-AudioFrame raises VADError."""
    mock_vad = MockVAD()
    with pytest.raises(VADError):
        mock_vad.process_frame("not_a_frame")  # type: ignore

    energy_vad = EnergyVAD()
    with pytest.raises(VADError):
        energy_vad.process_frame({"data": b""})  # type: ignore

    simple_vad = SimpleVADDetector()
    with pytest.raises(VADError):
        simple_vad.evaluate_frame(None)  # type: ignore


def test_energy_vad_speech_and_silence_from_pcm():
    """Verify EnergyVAD detects speech and silence by reading raw PCM samples directly,
    independent of frame.is_speech.
    """
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)

    # Synthetic speech frame has RMS ~ 11000, dBFS ~ -10 dBFS
    speech_frame = AudioFrame(
        data=MockMicrophoneSource().generate_synthetic_frame(is_speech=True).data,
        is_speech=False,  # Intentionally falsified frame.is_speech flag!
        frame_duration_ms=30,
    )
    res_speech = vad.process_frame(speech_frame)
    assert res_speech.is_speech is True
    assert res_speech.energy_db > -25.0
    assert res_speech.confidence >= 0.5

    vad.reset()

    # Synthetic silence frame has RMS = 0, dBFS = -100 dBFS
    silent_frame = AudioFrame(
        data=b"\x00" * 960,
        is_speech=True,  # Intentionally falsified frame.is_speech flag!
        frame_duration_ms=30,
    )
    res_silence = vad.process_frame(silent_frame)
    assert res_silence.is_speech is False
    assert res_silence.energy_db == -100.0
    assert res_silence.confidence < 0.5


def test_energy_vad_trigger_confirmation():
    """Verify trigger confirmation requires trigger_frames consecutive active frames."""
    # Requires 2 consecutive frames to activate speech
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=2, hangover_frames=0)
    mic = MockMicrophoneSource()

    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    silence_frame = mic.generate_synthetic_frame(is_speech=False)

    # Frame 1 of speech: trigger counter is 1, not yet active
    res1 = vad.process_frame(speech_frame)
    assert res1.is_speech is False

    # Interrupted by 1 frame of silence: resets trigger counter
    res_silence = vad.process_frame(silence_frame)
    assert res_silence.is_speech is False

    # Frame 1 of speech again
    res2 = vad.process_frame(speech_frame)
    assert res2.is_speech is False

    # Frame 2 of consecutive speech: trigger confirmed!
    res3 = vad.process_frame(speech_frame)
    assert res3.is_speech is True


def test_energy_vad_hangover_smoothing():
    """Verify hangover smoothing maintains speech status across silence gaps."""
    # 1 trigger frame to start, 3 hangover frames after drop
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=3)
    mic = MockMicrophoneSource()

    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    silence_frame = mic.generate_synthetic_frame(is_speech=False)

    # 1. Trigger speech
    res1 = vad.process_frame(speech_frame)
    assert res1.is_speech is True
    assert vad.is_speech_active is True

    # 2. Feed silence frames: hangover should keep is_speech=True for 3 frames
    res2 = vad.process_frame(silence_frame)
    assert res2.is_speech is True  # hangover 1
    res3 = vad.process_frame(silence_frame)
    assert res3.is_speech is True  # hangover 2
    res4 = vad.process_frame(silence_frame)
    assert res4.is_speech is True  # hangover 3

    # 3. 4th silence frame: hangover expired, state transitions to False
    res5 = vad.process_frame(silence_frame)
    assert res5.is_speech is False
    assert vad.is_speech_active is False


def test_energy_vad_reset():
    """Verify EnergyVAD reset clears hangover and trigger state."""
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=3)
    mic = MockMicrophoneSource()

    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    vad.process_frame(speech_frame)
    assert vad.is_speech_active is True

    vad.reset()
    assert vad.is_speech_active is False


def test_simple_vad_detector_state_transitions():
    """Verify SimpleVADDetector linear RMS threshold and full transition cycle:
    SILENCE -> SPEECH_START -> SPEECH -> SPEECH_END -> SILENCE.
    """
    vad = SimpleVADDetector(energy_threshold=500.0)
    mic = MockMicrophoneSource()

    silent = mic.generate_synthetic_frame(is_speech=False)
    speech = mic.generate_synthetic_frame(is_speech=True)

    # 1. Silence -> SILENCE
    e1 = vad.evaluate_frame(silent)
    assert e1.state == VADState.SILENCE

    # 2. Transition into speech -> SPEECH_START
    e2 = vad.evaluate_frame(speech)
    assert e2.state == VADState.SPEECH_START

    # 3. Continued speech -> SPEECH
    e3 = vad.evaluate_frame(speech)
    assert e3.state == VADState.SPEECH

    # 4. Transition out of speech -> SPEECH_END
    e4 = vad.evaluate_frame(silent)
    assert e4.state == VADState.SPEECH_END

    # 5. Continued silence -> SILENCE
    e5 = vad.evaluate_frame(silent)
    assert e5.state == VADState.SILENCE

    # Reset
    vad.reset()
    assert vad._in_speech is False


def test_rms_vs_dbfs_threshold_distinction():
    """Verify that SimpleVADDetector operates on linear RMS amplitude (e.g. 500.0)
    while EnergyVAD operates on logarithmic dBFS (e.g. -42.0 dBFS).
    """
    simple_vad = SimpleVADDetector(energy_threshold=500.0)
    energy_vad = EnergyVAD(threshold_db=-42.0)

    assert simple_vad.energy_threshold == 500.0  # Linear amplitude
    assert energy_vad.threshold_db == -42.0      # dBFS scale
