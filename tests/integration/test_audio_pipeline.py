"""
Integration tests for the complete Audio & VAD pipeline.
Located in tests/integration/ per SDK-9 testing strategy.

Verifies end-to-end integration:
MockMicrophoneSource -> AudioFrame stream -> VAD Detector -> EventEnvelope
conforming to SDK-9 Integration Contracts (docs/integration-contracts.md) and
the provisional Speech-to-Text audio-frame interface.
"""
import struct
import pytest

from packages.audio import (
    AudioConfig,
    AudioFrame,
    EnergyVAD,
    EventEnvelope,
    MockMicrophoneSource,
    SimpleVADDetector,
    VADState,
)


def test_end_to_end_audio_vad_pipeline():
    """Verify stream generation, VAD state transitions, and EventEnvelope emission."""
    config = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=20)

    # 60ms speech, 60ms silence, 60ms speech
    timeline = [("speech", 60), ("silence", 60), ("speech", 60)]
    mic = MockMicrophoneSource(
        config=config,
        pattern="custom",
        custom_timeline=timeline,
        max_frames=9,  # 180ms total / 20ms = 9 frames
    )

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=1)

    envelopes = []
    session_id = "session-integ-001"
    correlation_id = "corr-vad-001"
    last_state = False

    with mic:
        for frame in mic.stream():
            # Verify provisional contract fields on every frame
            assert isinstance(frame.data, bytes)
            assert len(frame.data) == 640
            assert frame.format == "s16le"
            assert frame.sample_rate == 16000
            assert frame.channels == 1
            assert frame.frame_duration_ms == 20
            assert frame.timestamp_ms == float(frame.sequence_number * 20)

            result = vad.process_frame(frame)

            # Detect state transitions and project EventEnvelope
            if result.is_speech and not last_state:
                envelopes.append(
                    EventEnvelope.create(
                        event_type="audio.vad.speech_start",
                        session_id=session_id,
                        correlation_id=correlation_id,
                        payload={
                            "frame_id": frame.frame_id,
                            "sequence_number": frame.sequence_number,
                            "timestamp_ms": frame.timestamp_ms,
                            "energy_db": result.energy_db,
                        },
                    )
                )
                last_state = True
            elif not result.is_speech and last_state:
                envelopes.append(
                    EventEnvelope.create(
                        event_type="audio.vad.speech_end",
                        session_id=session_id,
                        correlation_id=correlation_id,
                        payload={
                            "frame_id": frame.frame_id,
                            "sequence_number": frame.sequence_number,
                            "timestamp_ms": frame.timestamp_ms,
                            "energy_db": result.energy_db,
                        },
                    )
                )
                last_state = False

    # Verify event envelopes conform strictly to shared contracts
    assert len(envelopes) >= 2
    for evt in envelopes:
        d = evt.to_dict()
        assert d["schema_version"] == "1.0.0"
        assert d["producer"] == "packages.audio"
        assert d["session_id"] == session_id
        assert d["correlation_id"] == correlation_id
        assert d["event_type"] in {"audio.vad.speech_start", "audio.vad.speech_end"}
        assert "frame_id" in d["payload"]
        assert "sequence_number" in d["payload"]
        assert "timestamp_ms" in d["payload"]


def test_speech_to_text_provisional_frame_contract_20ms_and_30ms():
    """Verify frames conform to STT developer's proposed specifications:
    - Sample rate: 16000 Hz
    - Channels: 1 (mono)
    - Sample format: signed 16-bit little-endian PCM ("s16le")
    - Internal payload: raw Python bytes
    - Sizing: 20ms = 640 bytes, 30ms = 960 bytes
    - Monotonic sequence numbers and audio-relative timestamp_ms
    """
    # 1. Test 20ms frames (640 bytes)
    cfg20 = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=20)
    with MockMicrophoneSource(config=cfg20, pattern="speech", max_frames=3) as mic20:
        frames20 = list(mic20.stream())

    assert len(frames20) == 3
    for idx, f in enumerate(frames20):
        assert len(f.data) == 640
        assert len(f.audio_data) == 640
        assert f.sequence_number == idx
        assert f.timestamp_ms == float(idx * 20)
        assert f.sample_rate == 16000
        assert f.channels == 1
        assert f.format == "s16le"
        assert f.frame_duration_ms == 20
        samples = struct.unpack("<320h", f.data)
        assert all(-32768 <= s <= 32767 for s in samples)

    # 2. Test 30ms frames (960 bytes)
    cfg30 = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=30)
    with MockMicrophoneSource(config=cfg30, pattern="speech", max_frames=3) as mic30:
        frames30 = list(mic30.stream())

    assert len(frames30) == 3
    for idx, f in enumerate(frames30):
        assert len(f.data) == 960
        assert len(f.audio_data) == 960
        assert f.sequence_number == idx
        assert f.timestamp_ms == float(idx * 30)
        assert f.sample_rate == 16000
        assert f.channels == 1
        assert f.format == "s16le"
        assert f.frame_duration_ms == 30
        samples = struct.unpack("<480h", f.data)
        assert all(-32768 <= s <= 32767 for s in samples)


def test_pipeline_reset_and_reuse():
    """Verify that multiple consecutive stream runs reset cleanly without side effects."""
    config = AudioConfig(frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, max_frames=2)
    vad = SimpleVADDetector(energy_threshold=500.0)

    # Run 1
    mic.open()
    frames1 = list(mic.stream())
    mic.close()
    assert len(frames1) == 2

    vad.reset()

    # Run 2
    mic.open()
    frames2 = list(mic.stream())
    mic.close()
    assert len(frames2) == 2
