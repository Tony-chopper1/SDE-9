"""
Unit tests for audio event emission, dispatching, and session pipeline (Week 3 D15-16).
Owner: Satwik A (features/Satwik-week3)

Tests:
- Speech start event emission.
- Speech end event emission.
- Correct speech start/end ordering.
- Session ID propagation.
- Correlation ID propagation.
- Normalized audio event emission.
- Multiple speech segments in one session.
- Silence between speech segments.
- No duplicate speech transition events.
- Deterministic mock audio behavior.
- Clean stream completion via flush().
- Listener subscription and exception safety.
"""
from __future__ import annotations

import pytest

from packages.audio.events import (
    AudioEventDispatcher,
    AudioEventType,
    AudioSessionPipeline,
)
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import (
    AudioConfig,
    AudioFrame,
    EventEnvelope,
    VADState,
)
from packages.audio.vad import EnergyVAD, MockVAD


def test_speech_start_and_end_event_emission():
    """Verify automatic emission of speech_start and speech_end events across a speech burst."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    # 40ms silence (2 frames), 60ms speech (3 frames), 40ms silence (2 frames) = 7 frames (140ms)
    timeline = [("silence", 40), ("speech", 60), ("silence", 40)]
    mic = MockMicrophoneSource(config=config, pattern="custom", custom_timeline=timeline, max_frames=7)

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(
        session_id="session-test-001",
        correlation_id="corr-test-001",
        vad=vad,
        emit_chunk_events=True,
    )

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    events = pipeline.events
    assert len(events) >= 2

    speech_starts = [e for e in events if e.event_type == AudioEventType.SPEECH_START.value]
    speech_ends = [e for e in events if e.event_type == AudioEventType.SPEECH_END.value]

    assert len(speech_starts) == 1
    assert len(speech_ends) == 1

    start_ev = speech_starts[0]
    assert start_ev.session_id == "session-test-001"
    assert start_ev.correlation_id == "corr-test-001"
    assert start_ev.payload["state"] == VADState.SPEECH_START.value
    assert start_ev.payload["segment_index"] == 1
    assert "energy_db" in start_ev.payload
    assert "timestamp_ms" in start_ev.payload

    end_ev = speech_ends[0]
    assert end_ev.session_id == "session-test-001"
    assert end_ev.correlation_id == "corr-test-001"
    assert end_ev.payload["state"] == VADState.SPEECH_END.value
    assert end_ev.payload["speech_duration_ms"] > 0
    assert end_ev.payload["speech_frames_count"] == 3


def test_strict_event_ordering():
    """Verify that speech_start is emitted BEFORE the first speech chunk, and speech_end BEFORE trailing silence chunk."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    timeline = [("silence", 20), ("speech", 40), ("silence", 20)]
    mic = MockMicrophoneSource(config=config, pattern="custom", custom_timeline=timeline, max_frames=4)

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(
        session_id="session-order-001",
        correlation_id="corr-order-001",
        vad=vad,
        emit_chunk_events=True,
    )

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    events = pipeline.events
    # Expected sequence of event types:
    # Frame 0 (silence): [audio.chunk(is_speech=False)]
    # Frame 1 (speech): [speech_start, audio.chunk(is_speech=True)]
    # Frame 2 (speech): [audio.chunk(is_speech=True)]
    # Frame 3 (silence): [speech_end, audio.chunk(is_speech=False)]

    event_types = [e.event_type for e in events]
    assert event_types == [
        AudioEventType.AUDIO_CHUNK.value,       # Frame 0
        AudioEventType.SPEECH_START.value,       # Frame 1: start before chunk
        AudioEventType.AUDIO_CHUNK.value,       # Frame 1: speech chunk
        AudioEventType.AUDIO_CHUNK.value,       # Frame 2: speech chunk
        AudioEventType.SPEECH_END.value,         # Frame 3: end before chunk
        AudioEventType.AUDIO_CHUNK.value,       # Frame 3: silence chunk
    ]

    # Verify speech_start index precedes first speech chunk index
    start_idx = event_types.index(AudioEventType.SPEECH_START.value)
    first_speech_chunk_idx = start_idx + 1
    assert events[first_speech_chunk_idx].payload["is_speech"] is True


def test_session_and_correlation_id_propagation():
    """Verify every single emitted event carries the exact session_id and correlation_id."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, pattern="alternating", max_frames=6)

    custom_session = "sess-alpha-999"
    custom_corr = "corr-tracing-888"

    pipeline = AudioSessionPipeline(
        session_id=custom_session,
        correlation_id=custom_corr,
        emit_chunk_events=True,
    )

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    assert len(pipeline.events) >= 6
    for ev in pipeline.events:
        assert ev.session_id == custom_session
        assert ev.correlation_id == custom_corr
        assert ev.schema_version == "1.0.0"
        assert ev.producer == "packages.audio"
        assert ev.timestamp.endswith("+00:00") or ev.timestamp.endswith("Z")


def test_normalized_audio_chunk_events():
    """Verify audio.chunk normalized payload format, telemetry and optional base64 serialization."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, pattern="speech", max_frames=2)

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(
        session_id="session-chunk-test",
        vad=vad,
        include_raw_bytes_in_chunk=True,
    )

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    chunk_events = [e for e in pipeline.events if e.event_type == AudioEventType.AUDIO_CHUNK.value]
    assert len(chunk_events) == 2

    for ch in chunk_events:
        p = ch.payload
        assert "frame_id" in p
        assert "chunk_id" in p
        assert p["chunk_id"] == p["frame_id"]
        assert "frame_index" in p
        assert "sequence_number" in p
        assert "timestamp_ms" in p
        assert "timestamp_utc" in p
        assert p["sample_rate"] == 16000
        assert p["channels"] == 1
        assert p["format"] == "s16le"
        assert p["frame_duration_ms"] == 20
        assert p["byte_length"] == 640
        assert p["is_speech"] is True
        assert "rms" in p
        assert "dbfs" in p
        assert "audio_data_base64" in p
        assert len(p["audio_data_base64"]) > 0


def test_multiple_speech_segments_in_single_session():
    """Verify tracking of multiple distinct speech bursts separated by silence in a single session."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    # Burst 1: 40ms silence, 60ms speech, 40ms silence
    # Burst 2: 60ms speech, 40ms silence
    timeline = [
        ("silence", 40),
        ("speech", 60),
        ("silence", 40),
        ("speech", 60),
        ("silence", 40),
    ]
    mic = MockMicrophoneSource(config=config, pattern="custom", custom_timeline=timeline, max_frames=12)

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(session_id="multi-speech-session", vad=vad)

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    starts = [e for e in pipeline.events if e.event_type == AudioEventType.SPEECH_START.value]
    ends = [e for e in pipeline.events if e.event_type == AudioEventType.SPEECH_END.value]

    assert len(starts) == 2
    assert len(ends) == 2
    assert pipeline.speech_segments_count == 2

    # Segment indices must advance monotonically
    assert starts[0].payload["segment_index"] == 1
    assert ends[0].payload["segment_index"] == 1
    assert starts[1].payload["segment_index"] == 2
    assert ends[1].payload["segment_index"] == 2


def test_silence_between_speech_segments():
    """Verify that during prolonged silence, zero false speech transitions are emitted."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, pattern="silence", max_frames=8)

    pipeline = AudioSessionPipeline(session_id="silence-session", emit_chunk_events=True)

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    starts = [e for e in pipeline.events if e.event_type == AudioEventType.SPEECH_START.value]
    ends = [e for e in pipeline.events if e.event_type == AudioEventType.SPEECH_END.value]
    chunks = [e for e in pipeline.events if e.event_type == AudioEventType.AUDIO_CHUNK.value]

    assert len(starts) == 0
    assert len(ends) == 0
    assert len(chunks) == 8
    assert all(c.payload["is_speech"] is False for c in chunks)


def test_no_duplicate_speech_transition_events():
    """Verify speech_start is emitted exactly once per onset and not repeated on every continuous speech frame."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    # Continuous speech for 10 frames
    mic = MockMicrophoneSource(config=config, pattern="speech", max_frames=10)

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(session_id="continuous-speech", vad=vad)

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    starts = [e for e in pipeline.events if e.event_type == AudioEventType.SPEECH_START.value]
    assert len(starts) == 1
    assert starts[0].payload["frame_index"] == 0


def test_flush_bounds_active_speech_segment():
    """Verify pipeline flush cleanly terminates an ongoing speech segment upon stream end."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    # Stream ends while still speaking
    mic = MockMicrophoneSource(config=config, pattern="speech", max_frames=5)

    pipeline = AudioSessionPipeline(session_id="flush-test-session")

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    assert pipeline.in_speech is True
    trailing_events = pipeline.flush()

    assert pipeline.in_speech is False
    assert len(trailing_events) == 1
    assert trailing_events[0].event_type == AudioEventType.SPEECH_END.value
    assert trailing_events[0].payload["reason"] == "end_of_stream_flush"


def test_deterministic_mock_audio_events_behavior():
    """Verify two independent pipeline runs with identical mock mic configuration produce identical event sequences."""
    def run_pipeline():
        config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
        mic = MockMicrophoneSource(
            config=config,
            pattern="alternating",
            max_frames=6,
            seed=42,
            start_timestamp=1793491200.0,
        )
        vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
        pipe = AudioSessionPipeline(
            session_id="deterministic-session-001",
            correlation_id="deterministic-corr-001",
            vad=vad,
            emit_chunk_events=True,
        )
        with mic:
            for frame in mic.stream():
                pipe.process_frame(frame)
        return pipe.events

    events1 = run_pipeline()
    events2 = run_pipeline()

    assert len(events1) == len(events2)
    for e1, e2 in zip(events1, events2):
        assert e1.event_type == e2.event_type
        assert e1.session_id == e2.session_id
        assert e1.correlation_id == e2.correlation_id
        assert e1.payload["frame_id"] == e2.payload["frame_id"]
        assert e1.payload.get("timestamp_ms") == e2.payload.get("timestamp_ms")


def test_event_dispatcher_subscription_and_filtering():
    """Verify dispatcher observer pattern, type filtering, and resilient error handling."""
    dispatcher = AudioEventDispatcher()
    all_events: list[EventEnvelope] = []
    speech_only: list[EventEnvelope] = []

    def failing_listener(evt: EventEnvelope):
        raise RuntimeError("Faulty subscriber should not crash dispatcher")

    dispatcher.subscribe(lambda e: all_events.append(e))
    dispatcher.subscribe(lambda e: speech_only.append(e), event_type=AudioEventType.SPEECH_START.value)
    dispatcher.subscribe(failing_listener)

    pipeline = AudioSessionPipeline(
        session_id="sess-dispatch-001",
        dispatcher=dispatcher,
        emit_chunk_events=True,
    )

    f1 = AudioFrame(data=b"\x00" * 640, is_speech=False, frame_duration_ms=20)
    pipeline.process_frame(f1)

    assert len(all_events) == 1
    assert len(speech_only) == 0

    dispatcher.clear()
    assert len(dispatcher.history) == 0


def test_audio_frame_to_envelope_projection():
    """Verify AudioFrame.to_envelope() projects frame into compliant EventEnvelope."""
    frame = AudioFrame(
        data=b"\x00" * 640,
        sample_rate=16000,
        channels=1,
        format="s16le",
        frame_duration_ms=20,
        frame_index=5,
        sequence_number=5,
        timestamp_ms=100.0,
        is_speech=True,
    )
    envelope = frame.to_envelope(session_id="sess-frame-env", correlation_id="corr-frame-env")

    assert envelope.event_type == "audio.chunk"
    assert envelope.session_id == "sess-frame-env"
    assert envelope.correlation_id == "corr-frame-env"
    assert envelope.producer == "packages.audio"
    assert envelope.payload["frame_id"] == frame.frame_id
    assert envelope.payload["frame_index"] == 5
    assert envelope.payload["is_speech"] is True


def test_audio_chunk_envelope_json_serialization_and_pcm_decoding():
    """Verify all events produced by AudioSessionPipeline serialize cleanly to JSON and PCM decodes byte-for-byte."""
    import base64
    import json
    import math
    import struct

    pipeline = AudioSessionPipeline(session_id="sess-json-test", correlation_id="corr-json-test")
    # 20ms of 440Hz sine wave tone
    num_samples = 320
    samples = [int(12000 * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(num_samples)]
    raw_pcm = struct.pack(f"<{num_samples}h", *samples)

    frame = AudioFrame(
        data=raw_pcm,
        frame_id="frame-pcm-json-001",
        frame_index=1,
        sequence_number=1,
        timestamp_ms=20.0,
        sample_rate=16000,
        channels=1,
        frame_duration_ms=20,
        is_speech=True,
    )

    events = pipeline.process_frame(frame)
    assert len(events) >= 1

    for ev in events:
        # 1. JSON serialization must succeed without TypeError
        json_str = ev.to_json()
        assert isinstance(json_str, str)

        # 2. Deserialization must yield valid dictionary
        d = json.loads(json_str)
        assert d["event_id"] == ev.event_id
        assert d["event_type"] == ev.event_type
        assert d["session_id"] == "sess-json-test"
        assert d["correlation_id"] == "corr-json-test"

        # 3. For audio.chunk, verify base64 decodes back to original PCM bytes byte-for-byte
        if ev.event_type == AudioEventType.AUDIO_CHUNK.value:
            p = d["payload"]
            assert "audio_data_base64" in p
            decoded_pcm = base64.b64decode(p["audio_data_base64"])
            assert decoded_pcm == raw_pcm
            assert p["frame_id"] == "frame-pcm-json-001"
            assert p["sequence_number"] == 1
            assert p["timestamp_ms"] == 20.0
            assert p["byte_length"] == 640
            assert p["rms"] > 0
            assert "raw_pcm" not in p  # raw bytes must NOT be in payload

