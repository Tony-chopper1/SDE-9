from packages.audio import MockMicrophoneSource, SimpleVADDetector, VADState


def test_mock_microphone_generates_frames():
    mic = MockMicrophoneSource()
    frame = mic.generate_synthetic_frame(is_speech=True)

    assert frame.sample_rate == 16000
    assert len(frame.data) == 960  # 480 samples * 2 bytes
    assert frame.is_speech is True


def test_vad_detects_speech_and_silence():
    mic = MockMicrophoneSource()
    vad = SimpleVADDetector(energy_threshold=500.0)

    silence_frame = mic.generate_synthetic_frame(is_speech=False)
    silence_vad = vad.evaluate_frame(silence_frame)
    assert silence_vad.state == VADState.SILENCE

    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    speech_vad = vad.evaluate_frame(speech_frame)
    assert speech_vad.state == VADState.SPEECH
    assert speech_vad.energy_level > 500.0
