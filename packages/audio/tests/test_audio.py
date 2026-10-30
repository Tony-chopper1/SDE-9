"""
Unit Tests for Audio & VAD Module
Assigned Member: Satwik A (feature/audio-vad - Task W1)

TODO (Satwik A):
Write unit tests for MockMicrophoneSource and SimpleVADDetector to achieve >80% coverage.
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


# TODO (Satwik A): Uncomment and implement after completing mock_mic.py and vad.py
# def test_mock_microphone_generates_frames():
#     mic = MockMicrophoneSource()
#     mic.start_streaming()
#     frame = mic.generate_synthetic_frame(is_speech=True)
#     assert frame.is_speech is True
#     assert len(frame.data) == 960
#
# def test_vad_detects_speech_and_silence():
#     vad = SimpleVADDetector(energy_threshold=500.0)
#     ...
