"""
Unit Tests for Audio & VAD Module
Assigned Member: Satwik A (feature/audio-vad - Task W1)
"""
import pytest
from packages.audio import AudioConfig, AudioFrame, VADState, MockMicrophoneSource, SimpleVADDetector


def test_audio_models_instantiation():
    """Verify that AudioConfig and AudioFrame can be constructed."""
    config = AudioConfig(sample_rate=16000, bit_depth=16, channels=1)
    assert config.sample_rate == 16000

    frame = AudioFrame(data=b"\x00" * 960, sample_rate=16000, frame_index=1)
    assert len(frame.data) == 960
    assert frame.sample_rate == 16000


def test_mock_microphone_generates_frames():
    """Verify MockMicrophoneSource team interface produces valid 30ms frames."""
    mic = MockMicrophoneSource()
    mic.start_streaming()
    assert mic.is_streaming is True
    frame = mic.generate_synthetic_frame(is_speech=True)
    assert frame.is_speech is True
    assert len(frame.data) == 960
    assert frame.sample_rate == 16000
    assert frame.frame_duration_ms == 30
    mic.stop_streaming()
    assert mic.is_streaming is False


def test_vad_detects_speech_and_silence():
    """Verify SimpleVADDetector detects speech, silence, and transition states."""
    vad = SimpleVADDetector(energy_threshold=500.0)
    mic = MockMicrophoneSource()

    # 1. Silent frame -> SILENCE
    silent_frame = mic.generate_synthetic_frame(is_speech=False)
    evt_silent = vad.evaluate_frame(silent_frame)
    assert evt_silent.state == VADState.SILENCE
    assert evt_silent.energy_level < 500.0

    # 2. First speech frame -> SPEECH_START transition
    speech_frame1 = mic.generate_synthetic_frame(is_speech=True)
    evt_start = vad.evaluate_frame(speech_frame1)
    assert evt_start.state == VADState.SPEECH_START
    assert evt_start.energy_level >= 500.0

    # 3. Second speech frame -> continuous SPEECH
    speech_frame2 = mic.generate_synthetic_frame(is_speech=True)
    evt_speech = vad.evaluate_frame(speech_frame2)
    assert evt_speech.state == VADState.SPEECH
    assert evt_speech.energy_level >= 500.0

    # 4. Silent frame -> SPEECH_END transition
    silent_frame2 = mic.generate_synthetic_frame(is_speech=False)
    evt_end = vad.evaluate_frame(silent_frame2)
    assert evt_end.state == VADState.SPEECH_END
    assert evt_end.energy_level < 500.0

    # 5. Subsequent silent frame -> SILENCE
    silent_frame3 = mic.generate_synthetic_frame(is_speech=False)
    evt_silence_again = vad.evaluate_frame(silent_frame3)
    assert evt_silence_again.state == VADState.SILENCE
