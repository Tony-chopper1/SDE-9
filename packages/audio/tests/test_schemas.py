"""
Unit tests for Audio & VAD schemas, configurations, and event envelopes.
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
- Default and custom audio configurations
- Provisional STT interface fields (audio_data, sample_rate, channels, format, frame_duration_ms, sequence_number, timestamp_ms)
- Expected payload sizes (20ms -> 640 bytes, 30ms -> 960 bytes)
- Explicit rejection of empty audio frames as EOF
- Separate time semantics (timestamp vs timestamp_ms vs timestamp_utc)
- Internal VADEvent vs shared EventEnvelope
- SDK-9 error envelope compliance
"""
import pytest

from packages.audio.exceptions import (
    AudioConfigError,
    AudioError,
    AudioFrameValidationError,
)
from packages.audio.models import (
    AudioConfig,
    AudioFrame,
    EventEnvelope,
    VADEvent,
    VADResult,
    VADState,
)
import packages.audio.schemas as schemas


def test_default_audio_config():
    """Verify standard default audio configuration (16kHz, s16le, mono, 30ms)."""
    cfg = AudioConfig()
    assert cfg.sample_rate == 16000
    assert cfg.channels == 1
    assert cfg.bit_depth == 16
    assert cfg.format == "s16le"
    assert cfg.frame_duration_ms == 30
    assert cfg.bytes_per_sample == 2
    assert cfg.samples_per_frame == 480  # 16000 * 0.03
    assert cfg.frame_size_bytes == 960   # 480 * 1 * 2


def test_20ms_audio_config():
    """Verify 20ms frame duration produces exact expected 640 bytes (provisional STT contract)."""
    cfg = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=20)
    assert cfg.sample_rate == 16000
    assert cfg.frame_duration_ms == 20
    assert cfg.samples_per_frame == 320  # 16000 * 0.02
    assert cfg.frame_size_bytes == 640   # 320 * 1 * 2


def test_custom_supported_configs():
    """Verify other supported sample rates, channels, and frame durations."""
    cfg = AudioConfig(sample_rate=48000, channels=2, bit_depth=16, frame_duration_ms=10)
    assert cfg.samples_per_frame == 480  # 48000 * 0.01
    assert cfg.frame_size_bytes == 1920  # 480 * 2 * 2


def test_invalid_audio_configs():
    """Verify rejection of invalid sample rate, bit depth, channels, or format."""
    with pytest.raises(AudioConfigError) as exc_rate:
        AudioConfig(sample_rate=12345)
    assert "Unsupported sample rate" in str(exc_rate.value)
    assert exc_rate.value.code == "AUDIO_CONFIG_INVALID"

    with pytest.raises(AudioConfigError):
        AudioConfig(channels=4)

    with pytest.raises(AudioConfigError):
        AudioConfig(bit_depth=24)

    with pytest.raises(AudioConfigError):
        AudioConfig(format="flac")

    with pytest.raises(AudioConfigError):
        AudioConfig(frame_duration_ms=50)


def test_audio_config_serialization():
    """Verify dictionary serialization and Pydantic v2 compatibility."""
    cfg = AudioConfig(sample_rate=16000, channels=1, bit_depth=16, format="s16le", frame_duration_ms=20)
    d = cfg.to_dict()
    assert d == {
        "sample_rate": 16000,
        "channels": 1,
        "bit_depth": 16,
        "format": "s16le",
        "frame_duration_ms": 20,
    }
    assert cfg.model_dump() == d

    restored = AudioConfig.from_dict(d)
    assert restored == cfg
    assert AudioConfig.model_validate(d) == cfg


def test_stt_provisional_frame_fields_20ms():
    """Verify provisional STT interface fields on 20ms frame (640 bytes)."""
    payload_640 = b"\x00" * 640
    frame = AudioFrame(
        audio_data=payload_640,
        sample_rate=16000,
        channels=1,
        format="s16le",
        frame_duration_ms=20,
        sequence_number=5,
        timestamp_ms=100.0,
    )
    assert frame.audio_data == payload_640
    assert frame.data == payload_640
    assert frame.sample_rate == 16000
    assert frame.channels == 1
    assert frame.format == "s16le"
    assert frame.frame_duration_ms == 20
    assert frame.sequence_number == 5
    assert frame.frame_index == 5
    assert frame.timestamp_ms == 100.0
    assert frame.duration_ms == 20.0
    assert frame.calculate_rms() == 0.0
    assert frame.calculate_dbfs() == -100.0


def test_stt_provisional_frame_fields_30ms():
    """Verify provisional STT interface fields on 30ms frame (960 bytes)."""
    payload_960 = b"\x00" * 960
    frame = AudioFrame(
        data=payload_960,
        sample_rate=16000,
        channels=1,
        format="s16le",
        frame_duration_ms=30,
        frame_index=1,
        timestamp_ms=30.0,
    )
    assert len(frame.audio_data) == 960
    assert len(frame.data) == 960
    assert frame.frame_duration_ms == 30
    assert frame.sequence_number == 1
    assert frame.frame_index == 1
    assert frame.timestamp_ms == 30.0


def test_separate_timestamp_semantics():
    """Verify distinct semantics of timestamp (epoch sec), timestamp_ms (stream ms), timestamp_utc (ISO string)."""
    payload_960 = b"\x00" * 960
    frame = AudioFrame(
        data=payload_960,
        timestamp=1730304000.5,
        timestamp_ms=450.0,
        timestamp_utc="2026-10-30T14:30:00.500000+00:00",
        frame_duration_ms=30,
    )
    # Different units and meanings
    assert frame.timestamp == 1730304000.5           # Unix epoch seconds (float)
    assert frame.timestamp_ms == 450.0               # Stream offset in ms (float)
    assert "2026-10-30" in frame.timestamp_utc       # ISO 8601 UTC string


def test_empty_audio_frame_rejected_as_eos():
    """Verify empty frames are strictly rejected and cannot represent end-of-stream."""
    with pytest.raises(AudioFrameValidationError) as exc:
        AudioFrame(
            data=b"",
            sample_rate=16000,
            channels=1,
            format="s16le",
            frame_duration_ms=20,
        )
    assert "Empty audio frame rejected" in str(exc.value)
    assert "End-of-stream must be signaled via EOF" in str(exc.value)


def test_audio_frame_validation_failures():
    """Verify rejection of incorrect byte lengths and negative sequence numbers."""
    # Wrong byte length (expected 640, got 639)
    with pytest.raises(AudioFrameValidationError) as exc_len:
        AudioFrame(
            data=b"\x00" * 639,
            sequence_number=0,
            frame_duration_ms=20,
        )
    assert "byte length mismatch" in str(exc_len.value)
    assert exc_len.value.code == "AUDIO_FRAME_INVALID"

    # Negative sequence number
    with pytest.raises(AudioFrameValidationError):
        AudioFrame(
            data=b"\x00" * 640,
            sequence_number=-1,
            frame_duration_ms=20,
        )

    # Negative timestamp_ms
    with pytest.raises(AudioFrameValidationError):
        AudioFrame(
            data=b"\x00" * 640,
            timestamp_ms=-10.0,
            frame_duration_ms=20,
        )

    # Unsupported format
    with pytest.raises(AudioFrameValidationError):
        AudioFrame(
            data=b"\x00" * 640,
            format="alaw",
            frame_duration_ms=20,
        )


def test_audio_frame_serialization():
    """Verify dictionary serialization of AudioFrame."""
    frame = AudioFrame(
        data=b"\x00" * 640,
        sequence_number=42,
        timestamp_ms=840.0,
        frame_duration_ms=20,
    )
    d = frame.to_dict(include_raw_bytes=False)
    assert d["sequence_number"] == 42
    assert d["frame_index"] == 42
    assert d["timestamp_ms"] == 840.0
    assert d["sample_rate"] == 16000
    assert d["channels"] == 1
    assert d["format"] == "s16le"
    assert d["frame_duration_ms"] == 20
    assert d["byte_length"] == 640
    assert "audio_data_base64" not in d

    d_b64 = frame.to_dict(include_raw_bytes=True)
    assert "audio_data_base64" in d_b64


def test_vad_result_schema():
    """Verify VADResult schema."""
    res = VADResult(is_speech=True, confidence=0.88, energy_db=-24.5)
    assert res.is_speech is True
    assert res.confidence == 0.88
    assert res.energy_db == -24.5

    with pytest.raises(Exception):
        VADResult(is_speech=True, confidence=1.5, energy_db=0.0)


def test_internal_vad_event_and_envelope_projection():
    """Verify internal VADEvent and projection into shared SDK-9 EventEnvelope."""
    vad_evt = VADEvent(
        state=VADState.SPEECH_START,
        energy_level=1250.0,
        confidence=0.92,
        frame_index=15,
        timestamp_ms=300.0,
    )
    assert vad_evt.state == VADState.SPEECH_START
    assert vad_evt.energy_level == 1250.0
    assert vad_evt.confidence == 0.92
    assert vad_evt.frame_index == 15
    assert vad_evt.timestamp_ms == 300.0

    # Project to shared SDK-9 EventEnvelope
    envelope = vad_evt.to_envelope(
        session_id="session-xyz",
        correlation_id="corr-123",
    )
    assert isinstance(envelope, EventEnvelope)
    assert envelope.event_type == "audio.vad.speech_start"
    assert envelope.schema_version == "1.0.0"
    assert envelope.session_id == "session-xyz"
    assert envelope.correlation_id == "corr-123"
    assert envelope.producer == "packages.audio"
    assert envelope.payload["state"] == "SPEECH_START"
    assert envelope.payload["energy_level"] == 1250.0
    assert envelope.payload["frame_index"] == 15
    assert envelope.payload["timestamp_ms"] == 300.0


def test_event_envelope_create_and_json():
    """Verify EventEnvelope factory and json serialization."""
    env = EventEnvelope.create(
        event_type="audio.stream.started",
        session_id="session-001",
        payload={"sample_rate": 16000, "channels": 1},
    )
    assert env.event_type == "audio.stream.started"
    assert env.producer == "packages.audio"
    json_str = env.to_json()
    assert "audio.stream.started" in json_str
    assert "session-001" in json_str


def test_error_envelope_compliance():
    """Verify AudioError adheres to SDK-9 error envelope contract."""
    err = AudioError(
        message_safe_for_user="Audio device disconnected",
        code="AUDIO_DEVICE_LOST",
        retryable=True,
        correlation_id="req-123",
        details_redacted={"reason": "unplugged"},
    )
    env = err.to_envelope()
    assert env["code"] == "AUDIO_DEVICE_LOST"
    assert env["message_safe_for_user"] == "Audio device disconnected"
    assert env["retryable"] is True
    assert env["correlation_id"] == "req-123"
    assert env["details_redacted"] == {"reason": "unplugged"}


def test_schemas_compatibility_reexports():
    """Verify packages.audio.schemas cleanly re-exports all canonical models."""
    assert schemas.AudioConfig is AudioConfig
    assert schemas.AudioFrame is AudioFrame
    assert schemas.VADState is VADState
    assert schemas.VADEvent is VADEvent
    assert schemas.VADResult is VADResult
    assert schemas.EventEnvelope is EventEnvelope
