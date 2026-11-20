"""
Comprehensive Week 3 Contract & Integration Tests for Speech-to-Text Module.
Owner: Pavan (feature/pavan-week3) - Days 15-21

Acceptance Criteria Validated:
1. Days 15-16:
   - Session-linked revision and finalization events (transcript.interim, transcript.revised, transcript.final, transcript.utterance).
   - Every transcript event carries its session_id.
   - Configurable confidence threshold handles/tags low-confidence segments without crashing.
2. Days 17-18:
   - Cancellation cleanly stops in-flight transcription without dangling tasks or unhandled exceptions.
   - Quota or network failures seamlessly fall back to mock provider with normalized errors (zero raw exception leaks).
3. Days 19-20:
   - Out-of-order and missing-chunk resilience.
   - Audio frames and events flow into transcription.
   - Transcript events reach backend event stream (EventService / SSE) end-to-end in mock mode.
4. Day 21:
   - End-to-end pipeline verification without any external credentials or paid APIs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, List
from uuid import uuid4

import pytest

from packages.speech_to_text.accumulator import SegmentAccumulator
from packages.speech_to_text.event_stream import TranscriptEventBridge
from packages.speech_to_text.exceptions import (
    STTConnectionError,
    STTError,
    STTProviderError,
    STTQuotaExceededError,
    STTRateLimitError,
    STTTimeoutError,
    normalize_stt_exception,
)
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.models import (
    AccumulatedUtterance,
    TranscriptEvent,
    TranscriptSegment,
)
from packages.speech_to_text.orchestrator import (
    OrchestratorState,
    SpeechToTextOrchestrator,
)
from packages.speech_to_text.reconciler import TranscriptReconciler


# =============================================================================
# Mock Providers for Failure & Fallback Testing
# =============================================================================

class QuotaExceededTranscriber:
    """Simulates a cloud STT provider returning HTTP 429 / Quota Exhaustion."""
    def transcribe(self, audio_data: bytes, **kwargs):
        raise RuntimeError("Google Cloud Speech API error: 429 ResourceExhausted: Quota exceeded for project")


class NetworkFailureTranscriber:
    """Simulates an unexpected TCP / network disconnect during audio streaming."""
    def transcribe(self, audio_data: bytes, **kwargs):
        raise ConnectionResetError("STT gRPC stream connection reset by peer")


class TimeoutTranscriber:
    """Simulates a cloud provider gateway timeout."""
    def transcribe(self, audio_data: bytes, **kwargs):
        raise TimeoutError("Deadline exceeded waiting for cloud speech recognition")


# =============================================================================
# 1. Days 15-16: Session Association, Revision & Finalization, Confidence Tests
# =============================================================================

class TestWeek3SessionRevisionAndConfidence:
    """Validates session-linked events, revision tracking, and confidence thresholds."""

    def test_every_transcript_event_carries_session_id(self):
        """Acceptance Criteria: Every transcript event carries its session ID."""
        session_id = f"session-{uuid4()}"
        event = TranscriptEvent(
            session_id=session_id,
            event_type="transcript.segment",
            segment=TranscriptSegment(
                id="seg-1",
                text="testing session association",
                confidence=0.92,
                start_time=0.0,
                end_time=1.0,
                is_final=True,
            ),
        )
        assert event.session_id == session_id
        assert event.timestamp > 0.0
        assert event.event_id is not None
        assert event.schema_version == "1.0"
        assert event.producer == "speech_to_text"

    def test_transcript_event_rejects_empty_session_id(self):
        """Events must strictly reject missing or empty session IDs."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            TranscriptEvent(session_id="", event_type="transcript.interim")

        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            TranscriptEvent(session_id="   ", event_type="transcript.final")

    def test_interim_revised_and_final_event_lifecycle(self):
        """Acceptance Criteria: Interim results are revised and finalized with clear events."""
        session_id = f"session-{uuid4()}"
        reconciler = TranscriptReconciler(
            session_id=session_id,
            emit_revised_events=True,
        )

        # 1. First provisional interim segment
        seg_interim_1 = TranscriptSegment(
            id="draft-1",
            text="we need to",
            confidence=0.85,
            start_time=0.0,
            end_time=0.8,
            is_final=False,
        )
        ev1 = reconciler.process_segment(seg_interim_1)
        assert ev1 is not None
        assert ev1.event_type == "transcript.interim"
        assert ev1.session_id == session_id
        assert ev1.segment.text == "we need to"
        assert reconciler.get_full_transcript() == "we need to"

        # 2. Revised interim segment (user keeps speaking, expanding or revising draft)
        seg_interim_2 = TranscriptSegment(
            id="draft-2",
            text="we need to deploy the application",
            confidence=0.88,
            start_time=0.0,
            end_time=1.8,
            is_final=False,
        )
        ev2 = reconciler.process_segment(seg_interim_2)
        assert ev2 is not None
        assert ev2.event_type == "transcript.revised"
        assert ev2.session_id == session_id
        assert ev2.segment.text == "we need to deploy the application"
        assert reconciler.get_full_transcript() == "we need to deploy the application"

        # 3. Final commitment locking the phrase
        seg_final = TranscriptSegment(
            id="final-1",
            text="We need to deploy the application to production.",
            confidence=0.96,
            start_time=0.0,
            end_time=2.5,
            is_final=True,
        )
        ev3 = reconciler.process_segment(seg_final)
        assert ev3 is not None
        assert ev3.event_type == "transcript.final"
        assert ev3.session_id == session_id
        assert reconciler.active_interim is None
        assert "We need to deploy the application to production." in reconciler.get_finalized_text()

    def test_configurable_confidence_threshold_tagging(self):
        """Acceptance Criteria: Low-confidence segments are handled by a configurable threshold (Tagging mode)."""
        session_id = f"session-{uuid4()}"
        # Set threshold to 0.75; default action is "tag"
        reconciler = TranscriptReconciler(
            session_id=session_id,
            confidence_threshold=0.75,
            low_confidence_action="tag",
        )

        high_conf = TranscriptSegment(
            id="s1",
            text="clear and audible voice command",
            confidence=0.92,
            start_time=0.0,
            end_time=1.0,
            is_final=True,
        )
        ev_high = reconciler.process_segment(high_conf)
        assert ev_high is not None
        assert ev_high.segment.is_low_confidence is False

        low_conf = TranscriptSegment(
            id="s2",
            text="mumbled acoustic segment",
            confidence=0.45,
            start_time=1.1,
            end_time=2.0,
            is_final=True,
        )
        ev_low = reconciler.process_segment(low_conf)
        assert ev_low is not None
        # Must be tagged as low confidence
        assert ev_low.segment.is_low_confidence is True
        assert reconciler.low_confidence_count == 1

    def test_configurable_confidence_threshold_filtering(self):
        """Acceptance Criteria: Configurable threshold can suppress/filter sub-threshold noise chunks."""
        session_id = f"session-{uuid4()}"
        reconciler = TranscriptReconciler(
            session_id=session_id,
            confidence_threshold=0.70,
            low_confidence_action="filter",
        )

        noisy_seg = TranscriptSegment(
            id="noise-1",
            text="[unintelligible static]",
            confidence=0.30,
            start_time=0.0,
            end_time=0.5,
            is_final=True,
        )
        ev = reconciler.process_segment(noisy_seg)
        # Filter action suppresses delivery of low-confidence chunk
        assert ev is None
        assert reconciler.low_confidence_count == 1
        assert len(reconciler.finalized_segments) == 0


# =============================================================================
# 2. Days 17-18: Cancellation and Mock-Provider Fallback Tests
# =============================================================================

class TestWeek3CancellationAndFallback:
    """Validates in-flight cancellation and automatic fallback to mock provider."""

    def test_cancellation_stops_inflight_transcription_cleanly(self):
        """Acceptance Criteria: Cancellation stops in-flight transcription cleanly."""
        session_id = f"session-{uuid4()}"
        events_captured: List[TranscriptEvent] = []

        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            on_event=events_captured.append,
        )
        orchestrator.start()
        assert orchestrator.state == OrchestratorState.RUNNING

        # Push an audio chunk to fill the buffer
        orchestrator.push_audio(b"\x00\x01" * 800)  # 1600 bytes (partial chunk)
        assert len(orchestrator._buffered_pcm) > 0

        # Execute cancellation
        cancel_evt = orchestrator.cancel(reason="User clicked cancel button")
        assert orchestrator.state == OrchestratorState.CANCELLED
        assert cancel_evt.event_type == "transcript.cancelled"
        assert cancel_evt.session_id == session_id
        assert cancel_evt.details["reason"] == "User clicked cancel button"

        # Buffer must be cleared immediately without leaving dangling bytes
        assert len(orchestrator._buffered_pcm) == 0

        # Any audio pushed while cancelled must be safely ignored without raising
        result = orchestrator.push_audio(b"\x00\x02" * 1600)
        assert result == []

        # Flush while cancelled must return None
        assert orchestrator.flush() is None

        # Confirm cancellation event was emitted to subscribers
        assert any(e.event_type == "transcript.cancelled" for e in events_captured)

    def test_quota_failure_falls_back_to_mock_provider_with_normalized_error(self):
        """Acceptance Criteria: Quota failures fall back to mock provider with a normalized error."""
        session_id = f"session-{uuid4()}"
        events_emitted: List[TranscriptEvent] = []

        # Orchestrator configured with a primary provider that fails on quota
        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            transcriber=QuotaExceededTranscriber(),
            fallback_transcriber=FakeTranscriberService(),
            enable_fallback=True,
            on_event=events_emitted.append,
        )
        orchestrator.start()

        # Ingest full chunk (>= 3200 bytes) to trigger transcription
        audio_chunk = b"\x01\x00" * 2000  # 4000 bytes
        events = orchestrator.push_audio(audio_chunk)

        # Fallback occurred: stream did NOT crash
        assert orchestrator.is_fallback_active is True

        # Normalized fallback event was emitted
        fallback_evts = [e for e in events_emitted if e.event_type == "transcript.fallback"]
        assert len(fallback_evts) == 1
        fb_evt = fallback_evts[0]
        assert fb_evt.session_id == session_id
        assert fb_evt.is_fallback is True
        assert fb_evt.details["error_code"] == "STT_QUOTA_EXCEEDED"
        assert "FakeTranscriberService" in fb_evt.details["fallback_provider"]

        # Transcription output was successfully produced by the mock fallback provider
        assert len(events) >= 1
        final_text = orchestrator.get_full_transcript()
        assert len(final_text) > 0

    def test_network_failure_falls_back_to_mock_provider(self):
        """Acceptance Criteria: Network failures fall back to mock provider with normalized error."""
        session_id = f"session-{uuid4()}"
        events_emitted: List[TranscriptEvent] = []

        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            transcriber=NetworkFailureTranscriber(),
            fallback_transcriber=FakeTranscriberService(),
            enable_fallback=True,
            on_event=events_emitted.append,
        )
        orchestrator.start()

        audio_chunk = b"\x02\x00" * 2000  # 4000 bytes
        events = orchestrator.push_audio(audio_chunk)

        assert orchestrator.is_fallback_active is True
        fallback_evts = [e for e in events_emitted if e.event_type == "transcript.fallback"]
        assert len(fallback_evts) == 1
        assert fallback_evts[0].details["error_code"] == "STT_CONNECTION_ERROR"
        assert len(orchestrator.get_full_transcript()) > 0

    def test_zero_raw_exceptions_leak_when_fallback_disabled(self):
        """Normalized exceptions must be raised cleanly if fallback is explicitly disabled."""
        orchestrator = SpeechToTextOrchestrator(
            transcriber=QuotaExceededTranscriber(),
            enable_fallback=False,
        )
        orchestrator.start()

        # Must raise normalized STTQuotaExceededError, NOT raw RuntimeError
        with pytest.raises(STTQuotaExceededError) as exc_info:
            orchestrator.push_audio(b"\x01\x00" * 2000)

        err_envelope = exc_info.value.to_envelope()
        assert err_envelope["code"] == "STT_QUOTA_EXCEEDED"
        assert "Quota exceeded" in err_envelope["error"]


# =============================================================================
# 3. Days 19-20: Audio & Backend Event Stream Integration + Out-of-Order Tests
# =============================================================================

class TestWeek3AudioAndBackendStreamIntegration:
    """Validates audio event ingestion, chunk ordering/gaps, and backend event stream integration."""

    def test_out_of_order_chunks_handled_resiliently(self):
        """Acceptance Criteria: Tests cover out-of-order chunks."""
        session_id = f"session-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(session_id=session_id)
        orchestrator.start()

        chunk = b"\x01\x00" * 1600  # 3200 bytes

        # Push sequence numbers: 0, 2, 1, 4, 3 (disordered)
        orchestrator.push_audio(chunk, sequence_number=0)
        orchestrator.push_audio(chunk, sequence_number=2)
        orchestrator.push_audio(chunk, sequence_number=1)  # out of order!
        orchestrator.push_audio(chunk, sequence_number=4)
        orchestrator.push_audio(chunk, sequence_number=3)  # out of order!

        # Out-of-order counter must accurately track disordered packets
        assert orchestrator.out_of_order_chunks_count == 2
        # Full transcript must still be accumulated stably
        assert len(orchestrator.get_full_transcript()) > 0

    def test_missing_chunks_sequence_gaps_tracked(self):
        """Acceptance Criteria: Tests cover missing chunks."""
        session_id = f"session-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(session_id=session_id)
        orchestrator.start()

        chunk = b"\x01\x00" * 1600

        # Push seq 0, then skip directly to seq 5 (missing 1, 2, 3, 4 = 4 missing frames)
        orchestrator.push_audio(chunk, sequence_number=0)
        orchestrator.push_audio(chunk, sequence_number=5)

        assert orchestrator.missing_chunks_count == 4
        # System continues processing without halting
        assert orchestrator.state == OrchestratorState.RUNNING

    def test_audio_events_flow_into_transcription_via_bridge(self):
        """Acceptance Criteria: Audio events flow into transcription in mock mode."""
        from packages.audio import AudioConfig, MockMicrophoneSource
        from packages.audio.stt_bridge import AudioSTTBridge

        session_id = f"session-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(session_id=session_id)
        bridge = AudioSTTBridge(session_id=session_id, orchestrator=orchestrator)

        config = AudioConfig(sample_rate=16000, channels=1, frame_duration_ms=20)
        mic = MockMicrophoneSource(config=config, pattern="speech", max_frames=10)
        mic.open()

        frames_pushed = 0
        for frame in mic.stream():
            bridge.push_frame(frame, is_speech=True)
            frames_pushed += 1

        bridge.flush()
        assert frames_pushed == 10
        assert orchestrator.total_frames_processed > 0

    @pytest.mark.asyncio
    async def test_transcript_events_reach_backend_event_stream(self):
        """Acceptance Criteria: Transcript events reach backend event stream end to end in mock mode."""
        from backend.services.event_service import EventService
        from uuid import UUID

        session_uuid = uuid4()
        backend_event_service = EventService()

        # Wire up TranscriptEventBridge to backend EventService
        bridge = TranscriptEventBridge(event_service=backend_event_service)
        orchestrator = SpeechToTextOrchestrator(
            session_id=str(session_uuid),
            on_event=bridge.on_transcript_event,
            enable_revision_events=True,
        )
        orchestrator.start()

        # Ingest audio chunks
        chunk = b"\x02\x01" * 2000
        orchestrator.push_audio(chunk)
        orchestrator.finalize_utterance()
        await asyncio.sleep(0.05)

        # Verify backend EventService received transcript events
        published_records = backend_event_service.get_events(session_uuid)
        assert len(published_records) >= 1

        # Check payload format and producer attribution
        first_record = published_records[0]
        assert first_record.session_id == session_uuid
        assert first_record.producer == "speech_to_text"
        assert first_record.event_type.startswith("transcript.")
        assert "event_id" in first_record.payload
        assert first_record.payload["session_id"] == str(session_uuid)


# =============================================================================
# 4. Day 21: Full Pipeline Verification & Gate Tests
# =============================================================================

class TestWeek3GateAndContractParity:
    """Validates Day 21 gate: full mock-mode execution without real credentials."""

    def test_full_pipeline_mock_mode_no_credentials_required(self):
        """Acceptance Criteria: Pass with no real provider or API key."""
        session_id = f"gate-session-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            confidence_threshold=0.60,
            enable_revision_events=True,
        )
        orchestrator.start()

        # Push multiple synthetic speech frames
        for _ in range(5):
            orchestrator.push_audio(b"\x03\x00" * 1600, is_speech=True)

        utterance = orchestrator.stop()
        assert isinstance(utterance, AccumulatedUtterance)
        assert utterance.session_id == session_id
        assert len(utterance.full_text) > 0
        assert utterance.duration >= 0.0

    def test_no_duplicate_schemas_contract_parity(self):
        """Acceptance Criteria: No duplicate schemas; define each contract once."""
        event = TranscriptEvent(
            session_id="test-parity",
            event_type="transcript.final",
            segment=TranscriptSegment(
                id="seg-parity",
                text="Parity validation",
                confidence=0.99,
                start_time=0.0,
                end_time=1.0,
                is_final=True,
            ),
        )
        payload = event.to_backend_payload()
        assert payload["producer"] == "speech_to_text"
        assert payload["schema_version"] == "1.0"
        assert payload["payload"]["session_id"] == "test-parity"
