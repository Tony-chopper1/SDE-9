"""
Tests for Audio & VAD to Speech-to-Text Integration Bridge (D19-20).
Owner: Satwik A (features/Satwik-week3) - Week 3 (Days 19-20)

Validates:
1. Audio chunk reaches STT end to end in mock mode.
2. Speech boundaries are respected (only speech within speech_start..speech_end forwarded).
3. Silence is not incorrectly transcribed.
4. False VAD triggers do not cause incorrect speech delivery.
5. Chunk ordering and timestamps are preserved.
6. Gaps and delayed chunks are handled safely without crashing.
7. Device loss closes or safely terminates the active transcription segment.
8. Cancellation does not leave pending STT work.
9. Multiple sessions do not mix audio or transcripts.
10. No duplicate audio delivery occurs (frame_id deduplication).
11. Direct push_frame() helper functionality.
12. Full end-to-end integration: MockMicrophoneSource -> AudioSessionPipeline -> AudioSTTBridge -> STT.
"""
from __future__ import annotations

import math
import struct
import time
from typing import List

import pytest

from packages.audio.events import AudioEventDispatcher, AudioEventType, AudioSessionPipeline
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, EventEnvelope
from packages.audio.stt_bridge import AudioSTTBridge, MultiSessionSTTBridge
from packages.audio.vad import EnergyVAD
from packages.speech_to_text.models import TranscriptEvent
from packages.speech_to_text.orchestrator import OrchestratorState, SpeechToTextOrchestrator


def _make_speech_frame(seq: int = 0, timestamp_ms: float = 0.0, frame_id: str = "") -> AudioFrame:
    """Generate a 20ms 16kHz speech tone frame."""
    sample_rate = 16000
    num_samples = int(sample_rate * 0.02)  # 320 samples = 640 bytes
    samples = [int(15000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_samples)]
    raw = struct.pack(f"<{num_samples}h", *samples)
    fid = frame_id or f"frame-speech-{seq}"
    return AudioFrame(
        data=raw,
        frame_id=fid,
        frame_index=seq,
        sequence_number=seq,
        timestamp=timestamp_ms / 1000.0,
        timestamp_ms=timestamp_ms,
        frame_duration_ms=20,
        sample_rate=16000,
        channels=1,
        is_speech=True,
    )


def _make_silence_frame(seq: int = 0, timestamp_ms: float = 0.0, frame_id: str = "") -> AudioFrame:
    """Generate a 20ms 16kHz silence frame."""
    fid = frame_id or f"frame-silence-{seq}"
    return AudioFrame(
        data=b"\x00" * 640,
        frame_id=fid,
        frame_index=seq,
        sequence_number=seq,
        timestamp=timestamp_ms / 1000.0,
        timestamp_ms=timestamp_ms,
        frame_duration_ms=20,
        sample_rate=16000,
        channels=1,
        is_speech=False,
    )


def test_audio_chunk_reaches_stt_end_to_end_mock_mode():
    """Verify audio chunks flow end-to-end through dispatcher to STT orchestrator in mock mode."""
    dispatcher = AudioEventDispatcher()
    received_transcripts: List[TranscriptEvent] = []

    bridge = AudioSTTBridge(
        session_id="sess-e2e-01",
        dispatcher=dispatcher,
        on_transcript_event=lambda e: received_transcripts.append(e),
    )

    # Dispatch speech start
    start_env = EventEnvelope.create(
        event_type=AudioEventType.SPEECH_START.value,
        session_id="sess-e2e-01",
        payload={"frame_id": "frame-0", "sequence_number": 0},
    )
    dispatcher.dispatch(start_env)
    assert bridge.in_speech is True

    # Dispatch 6 speech chunks (6 * 640 bytes = 3840 bytes, exceeding min_chunk_bytes threshold of 3200)
    for i in range(6):
        frame = _make_speech_frame(seq=i, timestamp_ms=float(i * 20))
        chunk_env = EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-e2e-01",
            payload={
                "frame_id": frame.frame_id,
                "sequence_number": frame.sequence_number,
                "raw_pcm": frame.data,
                "sample_rate": 16000,
                "channels": 1,
                "timestamp": frame.timestamp,
                "is_speech": True,
            },
        )
        dispatcher.dispatch(chunk_env)

    # End speech and flush
    end_env = EventEnvelope.create(
        event_type=AudioEventType.SPEECH_END.value,
        session_id="sess-e2e-01",
        payload={"frame_id": "frame-6", "sequence_number": 6},
    )
    dispatcher.dispatch(end_env)

    assert bridge.in_speech is False
    assert bridge.telemetry["speech_chunks_forwarded"] == 6
    assert bridge.telemetry["silence_chunks_ignored"] == 0
    assert len(received_transcripts) >= 1

    transcript_text = bridge.get_full_transcript()
    assert len(transcript_text) > 0


def test_speech_boundaries_respected():
    """Verify audio chunks outside speech_start..speech_end boundaries are ignored."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-bounds-01", dispatcher=dispatcher)

    # Chunk arrived BEFORE speech_start
    f_before = _make_speech_frame(seq=0, frame_id="f-before")
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-bounds-01",
            payload={"frame_id": f_before.frame_id, "sequence_number": 0, "raw_pcm": f_before.data, "is_speech": True},
        )
    )
    # Not forwarded because in_speech is False
    assert bridge.telemetry["speech_chunks_forwarded"] == 0
    assert bridge.telemetry["silence_chunks_ignored"] == 1

    # Speech starts
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-bounds-01",
            payload={},
        )
    )
    assert bridge.in_speech is True

    # Chunk arrived WITHIN boundary
    f_within = _make_speech_frame(seq=1, frame_id="f-within")
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-bounds-01",
            payload={"frame_id": f_within.frame_id, "sequence_number": 1, "raw_pcm": f_within.data, "is_speech": True},
        )
    )
    assert bridge.telemetry["speech_chunks_forwarded"] == 1

    # Speech ends
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_END.value,
            session_id="sess-bounds-01",
            payload={},
        )
    )
    assert bridge.in_speech is False

    # Chunk arrived AFTER speech_end
    f_after = _make_speech_frame(seq=2, frame_id="f-after")
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-bounds-01",
            payload={"frame_id": f_after.frame_id, "sequence_number": 2, "raw_pcm": f_after.data, "is_speech": True},
        )
    )
    assert bridge.telemetry["speech_chunks_forwarded"] == 1
    assert bridge.telemetry["silence_chunks_ignored"] == 2


def test_silence_is_not_incorrectly_transcribed():
    """Verify silence frames (is_speech=False) are rejected even if in_speech is active."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-silence-01", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-silence-01",
            payload={},
        )
    )

    silence_frame = _make_silence_frame(seq=1)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-silence-01",
            payload={
                "frame_id": silence_frame.frame_id,
                "sequence_number": 1,
                "raw_pcm": silence_frame.data,
                "is_speech": False,  # Silence!
            },
        )
    )

    assert bridge.telemetry["speech_chunks_forwarded"] == 0
    assert bridge.telemetry["silence_chunks_ignored"] == 1


def test_false_vad_triggers_handled_cleanly():
    """Verify false VAD triggers (speech_start immediately followed by speech_end without speech frames) don't crash."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-false-trigger", dispatcher=dispatcher)

    # Rapid false trigger: speech_start followed immediately by speech_end
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-false-trigger",
            payload={},
        )
    )
    assert bridge.in_speech is True

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_END.value,
            session_id="sess-false-trigger",
            payload={},
        )
    )
    assert bridge.in_speech is False
    assert bridge.telemetry["speech_chunks_forwarded"] == 0
    assert bridge.get_full_transcript() == ""


def test_chunk_ordering_and_timestamps_preserved():
    """Verify monotonic sequence ordering and timestamps pass through to STT."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-order-01", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-order-01",
            payload={},
        )
    )

    for i in range(5):
        f = _make_speech_frame(seq=i, timestamp_ms=float(i * 20))
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="sess-order-01",
                payload={
                    "frame_id": f.frame_id,
                    "sequence_number": f.sequence_number,
                    "timestamp": f.timestamp,
                    "raw_pcm": f.data,
                    "is_speech": True,
                },
            )
        )

    assert bridge.telemetry["speech_chunks_forwarded"] == 5
    assert bridge.telemetry["out_of_order_chunks_dropped"] == 0


def test_gaps_and_delayed_chunks_handled_safely():
    """Verify out-of-order chunks are dropped and sequence gaps are tracked without throwing."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-gaps-01", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-gaps-01",
            payload={},
        )
    )

    # Deliver frame 0
    f0 = _make_speech_frame(seq=0)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-gaps-01",
            payload={"frame_id": f0.frame_id, "sequence_number": 0, "raw_pcm": f0.data, "is_speech": True},
        )
    )

    # Gap: skip frames 1 and 2, deliver frame 3
    f3 = _make_speech_frame(seq=3)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-gaps-01",
            payload={"frame_id": f3.frame_id, "sequence_number": 3, "raw_pcm": f3.data, "is_speech": True},
        )
    )
    assert bridge.telemetry["sequence_gaps_detected"] == 2
    assert bridge.telemetry["speech_chunks_forwarded"] == 2

    # Delayed/stale frame: frame 1 arrives after frame 3
    f1 = _make_speech_frame(seq=1)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-gaps-01",
            payload={"frame_id": f1.frame_id, "sequence_number": 1, "raw_pcm": f1.data, "is_speech": True},
        )
    )
    # Dropped as stale
    assert bridge.telemetry["out_of_order_chunks_dropped"] == 1
    assert bridge.telemetry["speech_chunks_forwarded"] == 2


def test_device_loss_closes_active_transcription_segment():
    """Verify device loss flushes any open transcription segment so utterances don't hang."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-loss-01", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-loss-01",
            payload={},
        )
    )

    # Push enough speech frames
    for i in range(5):
        f = _make_speech_frame(seq=i)
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="sess-loss-01",
                payload={"frame_id": f.frame_id, "sequence_number": i, "raw_pcm": f.data, "is_speech": True},
            )
        )

    assert bridge.in_speech is True

    # Device loss occurs
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.DEVICE_LOST.value,
            session_id="sess-loss-01",
            payload={"device_id": "mic-lost", "reason": "unplugged"},
        )
    )

    assert bridge.in_speech is False
    assert bridge.is_device_lost is True

    # Device recovered
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.DEVICE_RECOVERED.value,
            session_id="sess-loss-01",
            payload={"device_id": "mic-restored", "is_fallback": False},
        )
    )
    assert bridge.is_device_lost is False


def test_cancellation_terminates_stt_cleanly():
    """Verify stream cancellation terminates STT orchestrator without leaving pending work."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-cancel-01", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-cancel-01",
            payload={},
        )
    )

    f = _make_speech_frame(seq=0)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-cancel-01",
            payload={"frame_id": f.frame_id, "sequence_number": 0, "raw_pcm": f.data, "is_speech": True},
        )
    )

    # Cancel stream
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.STREAM_CANCELLED.value,
            session_id="sess-cancel-01",
            payload={"reason": "test_cancellation"},
        )
    )

    assert bridge.is_cancelled is True
    assert bridge.in_speech is False
    assert bridge.orchestrator.state == OrchestratorState.STOPPED

    # Subsequent chunks are ignored
    f2 = _make_speech_frame(seq=1)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-cancel-01",
            payload={"frame_id": f2.frame_id, "sequence_number": 1, "raw_pcm": f2.data, "is_speech": True},
        )
    )
    assert bridge.telemetry["speech_chunks_forwarded"] == 1


def test_multiple_sessions_isolated():
    """Verify MultiSessionSTTBridge isolates audio and transcripts between concurrent sessions."""
    dispatcher = AudioEventDispatcher()
    multi_bridge = MultiSessionSTTBridge(dispatcher=dispatcher)

    # Session A speech
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="session-A",
            payload={},
        )
    )
    for i in range(5):
        f = _make_speech_frame(seq=i, frame_id=f"a-{i}")
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="session-A",
                payload={"frame_id": f.frame_id, "sequence_number": i, "raw_pcm": f.data, "is_speech": True},
            )
        )
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_END.value,
            session_id="session-A",
            payload={},
        )
    )

    # Session B speech
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="session-B",
            payload={},
        )
    )
    for i in range(5):
        f = _make_speech_frame(seq=i, frame_id=f"b-{i}")
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="session-B",
                payload={"frame_id": f.frame_id, "sequence_number": i, "raw_pcm": f.data, "is_speech": True},
            )
        )
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_END.value,
            session_id="session-B",
            payload={},
        )
    )

    bridge_a = multi_bridge.get_or_create_session("session-A")
    bridge_b = multi_bridge.get_or_create_session("session-B")

    assert bridge_a.telemetry["speech_chunks_forwarded"] == 5
    assert bridge_b.telemetry["speech_chunks_forwarded"] == 5

    transcript_a = multi_bridge.get_session_transcript("session-A")
    transcript_b = multi_bridge.get_session_transcript("session-B")

    assert len(transcript_a) > 0
    assert len(transcript_b) > 0

    all_stopped = multi_bridge.stop_all()
    assert "session-A" in all_stopped
    assert "session-B" in all_stopped


def test_no_duplicate_audio_delivery():
    """Verify duplicate chunks with identical frame_ids are rejected."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-dedup", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-dedup",
            payload={},
        )
    )

    f = _make_speech_frame(seq=0, frame_id="unique-frame-123")

    # First delivery
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-dedup",
            payload={"frame_id": f.frame_id, "sequence_number": 0, "raw_pcm": f.data, "is_speech": True},
        )
    )

    # Duplicate delivery of identical frame_id
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-dedup",
            payload={"frame_id": f.frame_id, "sequence_number": 0, "raw_pcm": f.data, "is_speech": True},
        )
    )

    assert bridge.telemetry["speech_chunks_forwarded"] == 1
    assert bridge.telemetry["duplicate_chunks_dropped"] == 1


def test_direct_push_frame_helper():
    """Verify direct push_frame() helper forwards speech and ignores silence."""
    bridge = AudioSTTBridge(session_id="sess-direct")

    speech_f = _make_speech_frame(seq=0, frame_id="direct-speech-0")
    events = bridge.push_frame(speech_f)
    assert bridge.telemetry["speech_chunks_forwarded"] == 1

    silence_f = _make_silence_frame(seq=1, frame_id="direct-silence-1")
    silence_events = bridge.push_frame(silence_f)
    assert len(silence_events) == 0
    assert bridge.telemetry["silence_chunks_ignored"] == 1

    # Duplicate push
    dup_events = bridge.push_frame(speech_f)
    assert len(dup_events) == 0
    assert bridge.telemetry["duplicate_chunks_dropped"] == 1


def test_full_pipeline_to_bridge_integration():
    """End-to-end integration: MockMicrophoneSource -> AudioSessionPipeline -> AudioSTTBridge -> STT."""
    config = AudioConfig(sample_rate=16000, channels=1, frame_duration_ms=20)
    # 40ms silence (2 frames), 120ms speech (6 frames), 40ms silence (2 frames) = 10 frames (200ms)
    timeline = [("silence", 40), ("speech", 120), ("silence", 40)]
    mic = MockMicrophoneSource(
        config=config,
        pattern="custom",
        custom_timeline=timeline,
        max_frames=10,
    )

    dispatcher = AudioEventDispatcher()
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)

    pipeline = AudioSessionPipeline(
        session_id="full-integ-sess",
        correlation_id="full-integ-corr",
        vad=vad,
        dispatcher=dispatcher,
        emit_chunk_events=True,
    )

    bridge = AudioSTTBridge(
        session_id="full-integ-sess",
        dispatcher=dispatcher,
    )

    with mic:
        for frame in mic.stream():
            pipeline.process_frame(frame)

    pipeline.flush()

    assert bridge.telemetry["speech_chunks_forwarded"] == 6
    assert bridge.telemetry["silence_chunks_ignored"] == 4
    transcript = bridge.get_full_transcript()
    assert len(transcript) > 0

    utterance = bridge.finalize_utterance()
    assert utterance.is_complete is True
    assert utterance.session_id == "full-integ-sess"


def test_base64_encoded_audio_chunk_delivery():
    """Verify audio chunks with base64 encoded audio_data_base64 are decoded and forwarded."""
    import base64

    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-b64", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-b64",
            payload={},
        )
    )

    f = _make_speech_frame(seq=0)
    b64_str = base64.b64encode(f.data).decode("ascii")

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-b64",
            payload={
                "frame_id": f.frame_id,
                "sequence_number": 0,
                "audio_data_base64": b64_str,
                "is_speech": True,
            },
        )
    )

    assert bridge.telemetry["speech_chunks_forwarded"] == 1


def test_custom_orchestrator_injection_and_lifecycle():
    """Verify custom pre-configured orchestrator injection, flush, and stop methods."""
    custom_events: List[TranscriptEvent] = []
    custom_orch = SpeechToTextOrchestrator(
        session_id="sess-custom-orch",
        on_event=lambda e: custom_events.append(e),
    )

    bridge_events: List[TranscriptEvent] = []
    bridge = AudioSTTBridge(
        session_id="sess-custom-orch",
        orchestrator=custom_orch,
        on_transcript_event=lambda e: bridge_events.append(e),
    )

    f = _make_speech_frame(seq=0)
    bridge.push_frame(f)

    flushed = bridge.flush()
    # Stopping bridge stops orchestrator and finalizes utterance
    utt = bridge.stop()
    assert utt.session_id == "sess-custom-orch"
    assert bridge.is_cancelled is True

    # Pushing frame after stop returns []
    f2 = _make_speech_frame(seq=1)
    res = bridge.push_frame(f2)
    assert res == []


def test_multi_session_stop_session_and_callbacks():
    """Verify MultiSessionSTTBridge stop_session and transcript callbacks."""
    routed_events: List[tuple] = []
    multi_bridge = MultiSessionSTTBridge(
        on_transcript_event=lambda sid, ev: routed_events.append((sid, ev))
    )

    # Push to session 1
    bridge1 = multi_bridge.get_or_create_session("sess-1")
    f = _make_speech_frame(seq=0)
    bridge1.push_frame(f)

    # Stop session 1 specifically
    utt1 = multi_bridge.stop_session("sess-1")
    assert utt1 is not None
    assert utt1.session_id == "sess-1"

    # Stopping non-existent session returns None
    assert multi_bridge.stop_session("non-existent") is None
    assert multi_bridge.get_session_transcript("non-existent") == ""


def test_push_frame_when_device_lost_returns_empty():
    """Verify push_frame() returns [] when bridge is in device_lost state."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-loss-push", dispatcher=dispatcher)

    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.DEVICE_LOST.value,
            session_id="sess-loss-push",
            payload={},
        )
    )
    assert bridge.is_device_lost is True

    f = _make_speech_frame(seq=0)
    res = bridge.push_frame(f)
    assert res == []


def test_deduplication_cache_remains_bounded_large_scale():
    """Verify deduplication cache strictly adheres to dedup_capacity bound under large-scale load."""
    bridge = AudioSTTBridge(session_id="sess-bounded", dedup_capacity=50)

    # Push 200 distinct speech frames
    for i in range(200):
        f = _make_speech_frame(seq=i, frame_id=f"frame-unique-{i}")
        bridge.push_frame(f)

    assert len(bridge._delivered_frame_ids) == 50
    assert bridge.telemetry["speech_chunks_forwarded"] == 200

    # Oldest frames (e.g. 0..149) should have been evicted
    assert f"0:frame-unique-0" not in bridge._delivered_frame_ids
    # Most recent frames (e.g. 150..199) should be retained
    assert f"0:frame-unique-199" in bridge._delivered_frame_ids


def test_duplicate_frames_within_retained_window_rejected():
    """Verify duplicate frame IDs within the retained window are dropped."""
    bridge = AudioSTTBridge(session_id="sess-window-dedup", dedup_capacity=50)

    f1 = _make_speech_frame(seq=0, frame_id="frame-window-001")
    bridge.push_frame(f1)
    assert bridge.telemetry["speech_chunks_forwarded"] == 1

    # Push duplicate of f1
    bridge.push_frame(f1)
    assert bridge.telemetry["speech_chunks_forwarded"] == 1
    assert bridge.telemetry["duplicate_chunks_dropped"] == 1


def test_valid_frames_after_device_recovery_are_accepted():
    """Verify valid frames from newly created source restarting at sequence 0 after recovery are accepted."""
    dispatcher = AudioEventDispatcher()
    bridge = AudioSTTBridge(session_id="sess-recon-seq", dispatcher=dispatcher)

    # 1. Pre-loss: speech start and frames 0, 1, 2
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-recon-seq",
            payload={},
        )
    )
    for i in range(3):
        f = _make_speech_frame(seq=i, frame_id=f"frame-common-{i}")
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="sess-recon-seq",
                payload={"frame_id": f.frame_id, "sequence_number": i, "raw_pcm": f.data, "is_speech": True},
            )
        )
    assert bridge.telemetry["speech_chunks_forwarded"] == 3

    # 2. Device lost
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.DEVICE_LOST.value,
            session_id="sess-recon-seq",
            payload={"device_id": "mic-1"},
        )
    )
    assert bridge.is_device_lost is True

    # 3. Device recovered
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.DEVICE_RECOVERED.value,
            session_id="sess-recon-seq",
            payload={"device_id": "mic-1", "is_fallback": False},
        )
    )
    assert bridge.is_device_lost is False

    # 4. Post-recovery: speech start and new frames restarting at sequence 0 (with same frame_id)
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.SPEECH_START.value,
            session_id="sess-recon-seq",
            payload={},
        )
    )
    for i in range(3):
        f_new = _make_speech_frame(seq=i, frame_id=f"frame-common-{i}")
        dispatcher.dispatch(
            EventEnvelope.create(
                event_type=AudioEventType.AUDIO_CHUNK.value,
                session_id="sess-recon-seq",
                payload={"frame_id": f_new.frame_id, "sequence_number": i, "raw_pcm": f_new.data, "is_speech": True},
            )
        )

    # All 3 frames after recovery must be accepted, not dropped as stale or duplicate
    assert bridge.telemetry["speech_chunks_forwarded"] == 6
    assert bridge.telemetry["out_of_order_chunks_dropped"] == 0

    # 5. Pushing duplicate frame within post-recovery epoch is rejected
    f_dup = _make_speech_frame(seq=2, frame_id=f"frame-common-2")
    dispatcher.dispatch(
        EventEnvelope.create(
            event_type=AudioEventType.AUDIO_CHUNK.value,
            session_id="sess-recon-seq",
            payload={"frame_id": f_dup.frame_id, "sequence_number": 2, "raw_pcm": f_dup.data, "is_speech": True},
        )
    )
    assert bridge.telemetry["speech_chunks_forwarded"] == 6
    assert bridge.telemetry["duplicate_chunks_dropped"] == 1


