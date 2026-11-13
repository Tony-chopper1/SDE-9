"""
Comprehensive Unit & Integration Tests for Speech-to-Text Module.

Validates data models, strict input bounds, deterministic fake transcriber,
out-of-order segment accumulation, interim vs. final handling, and audio pipeline streaming.
"""
from __future__ import annotations

import os
import random
import pytest
from pydantic import ValidationError

from packages.speech_to_text.models import (
    AccumulatorState,
    TranscriptSegment,
    AccumulatedUtterance,
    TranscriptEvent,
)
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.accumulator import SegmentAccumulator


# =============================================================================
# 1. Transcript Data Models & Schema Validation Tests
# =============================================================================

class TestTranscriptModels:
    """Tests for TranscriptSegment, AccumulatedUtterance, and TranscriptEvent schemas."""

    def test_transcript_segment_validation(self):
        seg = TranscriptSegment(
            id="seg-1",
            text="Hello from AI Voice Co-Pilot",
            confidence=0.98,
            start_time=1.0,
            end_time=2.5,
            is_final=True,
            language="en",
        )
        assert seg.id == "seg-1"
        assert seg.confidence == 0.98
        assert seg.is_final is True
        assert seg.language == "en"

    def test_transcript_segment_confidence_bounds(self):
        """Confidence score must be strictly clamped between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            TranscriptSegment(
                id="seg-err",
                text="error",
                confidence=1.5,
                start_time=0.0,
                end_time=1.0,
            )

        with pytest.raises(ValidationError):
            TranscriptSegment(
                id="seg-err-neg",
                text="error",
                confidence=-0.1,
                start_time=0.0,
                end_time=1.0,
            )

    def test_transcript_segment_negative_start_time(self):
        """start_time cannot be negative."""
        with pytest.raises(ValidationError, match="start_time cannot be negative"):
            TranscriptSegment(
                id="seg-neg-start",
                text="test",
                start_time=-1.0,
                end_time=1.0,
            )

    def test_transcript_segment_negative_end_time(self):
        """end_time cannot be negative."""
        with pytest.raises(ValidationError, match="end_time cannot be negative"):
            TranscriptSegment(
                id="seg-neg-end",
                text="test",
                start_time=0.0,
                end_time=-0.5,
            )

    def test_transcript_segment_end_before_start(self):
        """end_time cannot be earlier than start_time."""
        with pytest.raises(ValidationError, match="cannot be earlier than start_time"):
            TranscriptSegment(
                id="seg-inverted",
                text="test",
                start_time=5.0,
                end_time=2.0,
            )

    def test_transcript_segment_empty_id(self):
        """Segment id cannot be empty or whitespace."""
        with pytest.raises(ValidationError, match="Segment id cannot be empty"):
            TranscriptSegment(
                id="",
                text="test",
                start_time=0.0,
                end_time=1.0,
            )
        with pytest.raises(ValidationError, match="Segment id cannot be empty"):
            TranscriptSegment(
                id="   ",
                text="test",
                start_time=0.0,
                end_time=1.0,
            )

    def test_accumulated_utterance_model(self):
        utterance = AccumulatedUtterance(
            id="utt-1",
            session_id="sess-100",
            full_text="Test sentence",
            start_time=0.0,
            end_time=3.0,
            duration=3.0,
            is_complete=True,
        )
        assert utterance.duration == 3.0
        assert utterance.is_complete is True

    def test_accumulated_utterance_duration_auto_calculation(self):
        """Auto-computes duration when duration is 0.0."""
        utterance = AccumulatedUtterance(
            id="utt-auto",
            session_id="sess-100",
            full_text="Auto duration",
            start_time=1.5,
            end_time=4.5,
            duration=0.0,
        )
        assert utterance.duration == 3.0

    def test_accumulated_utterance_invalid_time_inversion(self):
        """end_time cannot be less than start_time."""
        with pytest.raises(ValidationError, match="end_time cannot be less than start_time"):
            AccumulatedUtterance(
                id="utt-inv",
                session_id="s1",
                full_text="Error",
                start_time=5.0,
                end_time=2.0,
            )

    def test_transcript_event_model(self):
        event = TranscriptEvent(
            session_id="sess-100",
            segment=TranscriptSegment(
                id="seg-e1",
                text="Speech event",
                start_time=0.0,
                end_time=1.0,
            ),
        )
        assert event.event_type == "transcript.segment"
        assert event.segment.text == "Speech event"

    def test_transcript_event_custom_event_type_and_timestamp(self):
        """Verify custom event types and explicit timestamp on TranscriptEvent."""
        custom_ts = 1700000000.5
        event = TranscriptEvent(
            event_type="transcript.finalized",
            session_id="sess-custom-event",
            utterance=AccumulatedUtterance(
                id="utt-custom",
                session_id="sess-custom-event",
                full_text="Done speaking",
                start_time=0.0,
                end_time=2.0,
                duration=2.0,
            ),
            timestamp=custom_ts,
        )
        assert event.event_type == "transcript.finalized"
        assert event.timestamp == custom_ts
        assert event.utterance.full_text == "Done speaking"

    def test_typescript_definitions_file_exists(self):
        """Verifies deliverable: Create TypeScript type definitions."""
        ts_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "types.ts",
        )
        assert os.path.exists(ts_path)
        with open(ts_path, "r") as f:
            content = f.read()
        assert "export interface TranscriptSegment" in content
        assert "export interface AccumulatedUtterance" in content
        assert "export type AccumulatorState" in content


# =============================================================================
# 2. Fake Transcriber Service Tests (Determinism & Confidence Scoring)
# =============================================================================

class TestFakeTranscriberService:
    """Tests for FakeTranscriberService determinism, scoring, and streaming simulation."""

    def test_transcribe_empty_audio_returns_empty(self):
        service = FakeTranscriberService()
        result = service.transcribe(b"")
        assert result == []

    def test_confidence_scoring_logic(self):
        service = FakeTranscriberService()
        # Empty audio or phrase -> 0.0 confidence
        assert service.calculate_confidence(b"", "Hello") == 0.0
        assert service.calculate_confidence(b"\x00" * 1000, "") == 0.0

        # Small audio buffer receives penalty
        score_small = service.calculate_confidence(b"\x00" * 100, "Why is this code failing?")
        # Sufficient audio buffer receives high score
        score_full = service.calculate_confidence(b"\x00" * 3200, "Why is this code failing?")
        assert score_full > score_small
        assert 0.0 <= score_full <= 1.0

        # Final segment should score higher than interim partial
        score_interim = service.calculate_confidence(b"\x00" * 3200, "Why is this", is_final=False)
        score_final = service.calculate_confidence(b"\x00" * 3200, "Why is this", is_final=True)
        assert score_final > score_interim

    def test_fake_transcriber_strictly_deterministic_without_offset(self):
        """
        CRITICAL FIX: Calling transcribe() multiple times with offset=0 (or default)
        must produce IDENTICAL timestamps, segment IDs, and text without time.time() drift.
        """
        service = FakeTranscriberService()
        dummy_audio = b"\x00" * 3200

        res1 = service.transcribe(dummy_audio, phrase_index=0)
        res2 = service.transcribe(dummy_audio, phrase_index=0)

        assert len(res1) == 1
        assert len(res2) == 1

        seg1 = res1[0]
        seg2 = res2[0]

        assert seg1.id == seg2.id
        assert seg1.start_time == seg2.start_time == 0.0
        assert seg1.end_time == seg2.end_time
        assert seg1.text == seg2.text
        assert seg1.confidence == seg2.confidence
        assert seg1.is_final == seg2.is_final

    def test_simulate_streaming_chunks_strictly_deterministic(self):
        """
        CRITICAL FIX: simulate_streaming_chunks() without offset produces
        identical segment sequences across repeated executions.
        """
        service = FakeTranscriberService()
        chunks1 = service.simulate_streaming_chunks(phrase_index=1)
        chunks2 = service.simulate_streaming_chunks(phrase_index=1)

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.id == c2.id
            assert c1.text == c2.text
            assert c1.start_time == c2.start_time
            assert c1.end_time == c2.end_time
            assert c1.confidence == c2.confidence
            assert c1.is_final == c2.is_final

    def test_transcribe_custom_default_base_time(self):
        """Configuring default_base_time in __init__ applies when offset is 0."""
        service = FakeTranscriberService(default_base_time=50.0)
        res = service.transcribe(b"\x00" * 3200, phrase_index=0, start_time_offset=0.0)
        assert res[0].start_time == 50.0
        assert res[0].end_time > 50.0

    def test_transcribe_with_custom_timestamp(self):
        service = FakeTranscriberService()
        fixed_time = 1000.0
        res = service.transcribe(b"\x00" * 1000, phrase_index=2, start_time_offset=fixed_time)
        assert res[0].start_time == fixed_time
        assert res[0].end_time > fixed_time

    def test_transcribe_negative_phrase_index(self):
        """Negative phrase index is handled safely by wrapping around."""
        service = FakeTranscriberService()
        res = service.transcribe(b"\x00" * 1000, phrase_index=-1)
        assert len(res) == 1
        assert len(res[0].text) > 0

    def test_transcribe_deterministic_phrases(self):
        service = FakeTranscriberService()
        dummy_audio = b"\x00" * 3200  # 100ms of audio

        # Phrase 0: UC-02 Error
        res0 = service.transcribe(dummy_audio, phrase_index=0)
        assert len(res0) == 1
        assert "error" in res0[0].text.lower()
        assert res0[0].confidence >= 0.95
        assert res0[0].is_final is True

        # Phrase 1: UC-07 Multi-Step
        res1 = service.transcribe(dummy_audio, phrase_index=1)
        assert "project report" in res1[0].text.lower()

    def test_simulate_streaming_chunks(self):
        service = FakeTranscriberService()
        chunks = service.simulate_streaming_chunks(phrase_index=0, start_time_offset=5.0)

        assert len(chunks) > 1
        # Intermediary chunks should be partial (is_final=False)
        assert chunks[0].is_final is False
        # Last chunk should be final (is_final=True)
        assert chunks[-1].is_final is True
        assert "error" in chunks[-1].text.lower()

    def test_transcribe_with_different_languages(self):
        """Verifies language tag configuration on generated segments."""
        service_es = FakeTranscriberService(default_language="es")
        res_es = service_es.transcribe(b"\x00" * 3200, phrase_index=0)
        assert res_es[0].language == "es"

        service_fr = FakeTranscriberService(default_language="fr")
        chunks_fr = service_fr.simulate_streaming_chunks(phrase_index=0)
        assert all(c.language == "fr" for c in chunks_fr)

    def test_confidence_calculation_boundary_penalties(self):
        """Verify audio factor scaling across buffer size boundary conditions."""
        service = FakeTranscriberService()
        # Exactly 0 bytes
        assert service.calculate_confidence(b"", "Test phrase") == 0.0
        # 160 bytes: exactly half of 320 threshold -> factor 0.5
        score_half = service.calculate_confidence(b"\x00" * 160, "Test phrase", is_final=True)
        # 320 bytes: exactly at threshold -> factor 1.0
        score_full = service.calculate_confidence(b"\x00" * 320, "Test phrase", is_final=True)
        assert score_full > score_half
        # Extremely large buffer (1MB) -> clamped to 1.0 maximum
        score_large = service.calculate_confidence(b"\x00" * (1024 * 1024), "Test phrase with many words for bonus", is_final=True)
        assert 0.0 <= score_large <= 1.0

    def test_transcribe_all_mock_phrases(self):
        """Verify every single mock phrase produces valid, complete segments."""
        service = FakeTranscriberService()
        dummy_audio = b"\x00" * 3200
        for i, phrase in enumerate(service.MOCK_PHRASES):
            res = service.transcribe(dummy_audio, phrase_index=i)
            assert len(res) == 1
            assert res[0].text == phrase
            assert res[0].is_final is True
            assert (res[0].end_time - res[0].start_time) > 0.0
            assert 0.0 <= res[0].confidence <= 1.0

    def test_streaming_chunks_all_phrases(self):
        """Verify streaming chunk properties across all simulated phrases."""
        service = FakeTranscriberService()
        for i in range(len(service.MOCK_PHRASES)):
            chunks = service.simulate_streaming_chunks(phrase_index=i, start_time_offset=10.0)
            assert len(chunks) > 0
            # All intermediate chunks must be interim
            for c in chunks[:-1]:
                assert c.is_final is False
            # Final chunk must be committed
            assert chunks[-1].is_final is True
            assert chunks[-1].text == service.MOCK_PHRASES[i]
            # Monotonic timestamps
            for j in range(len(chunks) - 1):
                assert chunks[j + 1].start_time >= chunks[j].start_time


# =============================================================================
# 3. Segment Accumulator Tests: State Machine, Ordering & Interims
# =============================================================================

class TestSegmentAccumulator:
    """Tests for SegmentAccumulator ordering, deduplication, interim handling, and resets."""

    def test_initial_state_is_idle(self):
        acc = SegmentAccumulator(session_id="sess-1")
        assert acc.state == AccumulatorState.IDLE
        assert acc.count == 0
        assert acc.interim_text == ""

    def test_accumulator_session_id_validation(self):
        """Invalid session_id raises ValueError."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            SegmentAccumulator(session_id="")
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            SegmentAccumulator(session_id="   ")

    def test_accumulator_invalid_segment_type(self):
        """Passing non-TranscriptSegment raises TypeError."""
        acc = SegmentAccumulator(session_id="sess-1")
        with pytest.raises(TypeError, match="Expected TranscriptSegment instance"):
            acc.add_segment("not a segment")  # type: ignore
        with pytest.raises(TypeError):
            acc.add_segment(None)  # type: ignore

    def test_chronological_ordering_of_out_of_order_chunks(self):
        """Basic out-of-order 2-chunk insertion."""
        acc = SegmentAccumulator(session_id="sess-1")
        seg_second = TranscriptSegment(id="s2", text="world", start_time=1.1, end_time=2.0)
        seg_first = TranscriptSegment(id="s1", text="Hello", start_time=0.0, end_time=1.0)

        acc.add_segment(seg_second)
        acc.add_segment(seg_first)

        ordered = acc.current_segments
        assert ordered[0].text == "Hello"
        assert ordered[1].text == "world"

    def test_ordering_reverse_arrival(self):
        """Adding segments in exact reverse order (4, 3, 2, 1, 0) sorts correctly."""
        acc = SegmentAccumulator(session_id="sess-rev")
        segments = [
            TranscriptSegment(id=f"s{i}", text=f"word{i}", start_time=float(i), end_time=float(i) + 0.9)
            for i in range(5)
        ]

        # Add in reverse order
        for s in reversed(segments):
            acc.add_segment(s)

        ordered = acc.current_segments
        assert [s.id for s in ordered] == ["s0", "s1", "s2", "s3", "s4"]
        assert [s.text for s in ordered] == ["word0", "word1", "word2", "word3", "word4"]

    def test_ordering_shuffled_arrival(self):
        """Adding multiple randomized chunks preserves strict chronological order."""
        acc = SegmentAccumulator(session_id="sess-shuffle")
        segments = [
            TranscriptSegment(id=f"s{i}", text=f"token{i}", start_time=float(i) * 0.5, end_time=(float(i) + 1) * 0.5)
            for i in range(10)
        ]

        shuffled = list(segments)
        random.seed(42)
        random.shuffle(shuffled)

        for s in shuffled:
            acc.add_segment(s)

        ordered = acc.current_segments
        assert [s.id for s in ordered] == [f"s{i}" for i in range(10)]

    def test_ordering_identical_timestamps_tie_breaking(self):
        """Two segments with identical start_time and end_time are preserved."""
        acc = SegmentAccumulator(session_id="sess-ties")
        seg1 = TranscriptSegment(id="tie-1", text="Echo A", start_time=1.0, end_time=2.0)
        seg2 = TranscriptSegment(id="tie-2", text="Echo B", start_time=1.0, end_time=2.0)

        acc.add_segment(seg1)
        acc.add_segment(seg2)
        assert acc.count == 2
        assert {s.id for s in acc.current_segments} == {"tie-1", "tie-2"}

    def test_ordering_same_start_different_end(self):
        """Segments with identical start_time are sorted by end_time."""
        acc = SegmentAccumulator(session_id="sess-end-sort")
        seg_longer = TranscriptSegment(id="long", text="Long", start_time=1.0, end_time=4.0)
        seg_shorter = TranscriptSegment(id="short", text="Short", start_time=1.0, end_time=2.0)

        acc.add_segment(seg_longer)
        acc.add_segment(seg_shorter)

        ordered = acc.current_segments
        assert ordered[0].id == "short"
        assert ordered[1].id == "long"

    def test_ordering_enclosed_overlap(self):
        """Enclosed overlap computes overall span correctly."""
        acc = SegmentAccumulator(session_id="sess-enclosed")
        seg_outer = TranscriptSegment(id="outer", text="Outer", start_time=0.0, end_time=6.0)
        seg_inner = TranscriptSegment(id="inner", text="Inner", start_time=1.0, end_time=3.0)

        acc.add_segment(seg_inner)
        acc.add_segment(seg_outer)

        utterance = acc.finalize_utterance()
        assert utterance.start_time == 0.0
        assert utterance.end_time == 6.0
        assert utterance.duration == 6.0

    def test_interim_segment_update_overwriting(self):
        """Interim segment is replaced in place when a final segment with same ID arrives."""
        acc = SegmentAccumulator(session_id="sess-1")

        interim = TranscriptSegment(
            id="chunk-1",
            text="Why is this",
            confidence=0.8,
            start_time=0.0,
            end_time=1.0,
            is_final=False,
        )
        acc.add_segment(interim)
        assert acc.count == 1
        assert acc.current_segments[0].text == "Why is this"
        assert acc.interim_text == "Why is this"

        # Final commitment arrived for chunk-1
        final = TranscriptSegment(
            id="chunk-1",
            text="Why is this application",
            confidence=0.98,
            start_time=0.0,
            end_time=1.2,
            is_final=True,
        )
        acc.add_segment(final)

        assert acc.count == 1
        assert acc.current_segments[0].text == "Why is this application"
        assert acc.current_segments[0].is_final is True

    def test_interim_text_live_updates(self):
        """Property interim_text tracks latest preview during word-by-word streaming."""
        acc = SegmentAccumulator(session_id="sess-stream")

        chunk1 = TranscriptSegment(id="c1", text="Find", start_time=0.0, end_time=0.3, is_final=False)
        chunk2 = TranscriptSegment(id="c1", text="Find my", start_time=0.0, end_time=0.6, is_final=False)
        chunk3 = TranscriptSegment(id="c1", text="Find my report", start_time=0.0, end_time=0.9, is_final=True)

        acc.add_segment(chunk1)
        assert acc.interim_text == "Find"

        acc.add_segment(chunk2)
        assert acc.interim_text == "Find my"

        acc.add_segment(chunk3)
        assert acc.interim_text == "Find my report"

    def test_final_only_utterance_text_priority(self):
        """finalize_utterance() prefers final committed segments over lingering interim chunks."""
        acc = SegmentAccumulator(session_id="sess-mixed")
        seg_final1 = TranscriptSegment(id="f1", text="Open the file", start_time=0.0, end_time=1.0, is_final=True)
        seg_final2 = TranscriptSegment(id="f2", text="and inspect", start_time=1.1, end_time=2.0, is_final=True)
        seg_interim = TranscriptSegment(id="i1", text="now", start_time=2.1, end_time=2.5, is_final=False)

        acc.add_segment(seg_final1)
        acc.add_segment(seg_final2)
        acc.add_segment(seg_interim)

        utterance = acc.finalize_utterance()
        # Full text should prioritize final segments
        assert utterance.full_text == "Open the file and inspect"
        assert len(utterance.segments) == 3

    def test_interim_only_utterance_fallback(self):
        """If all segments are interim when finalized, text is not dropped."""
        acc = SegmentAccumulator(session_id="sess-interim-only")
        seg_interim = TranscriptSegment(id="i1", text="In-flight voice command", start_time=0.0, end_time=1.5, is_final=False)
        acc.add_segment(seg_interim)

        utterance = acc.finalize_utterance()
        assert utterance.full_text == "In-flight voice command"
        assert utterance.duration == 1.5

    def test_consecutive_utterance_lifecycle(self):
        """Accumulating, finalizing, and accumulating again increments utterance IDs and isolates state."""
        acc = SegmentAccumulator(session_id="sess-lifecycle")

        # First Utterance
        acc.add_segment(TranscriptSegment(id="u1-s1", text="Hello co-pilot", start_time=0.0, end_time=1.0))
        utt1 = acc.finalize_utterance()
        assert utt1.full_text == "Hello co-pilot"
        assert acc.state == AccumulatorState.IDLE
        assert acc.count == 0

        # Second Utterance
        acc.add_segment(TranscriptSegment(id="u2-s1", text="How are you?", start_time=2.0, end_time=3.0))
        utt2 = acc.finalize_utterance()
        assert utt2.full_text == "How are you?"
        assert utt1.id != utt2.id

    def test_add_segment_after_finalization_auto_resets(self):
        """Adding a segment when state is FINALIZED triggers automatic buffer reset."""
        acc = SegmentAccumulator(session_id="sess-auto-reset")
        acc.add_segment(TranscriptSegment(id="s1", text="First chunk", start_time=0.0, end_time=1.0))
        acc._state = AccumulatorState.FINALIZED
        acc.add_segment(TranscriptSegment(id="s2", text="Second chunk", start_time=1.0, end_time=2.0))
        assert acc.state == AccumulatorState.ACCUMULATING
        assert acc.count == 1
        assert acc.current_segments[0].text == "Second chunk"

    def test_pause_and_resume_state_transitions(self):
        acc = SegmentAccumulator(session_id="sess-1")
        acc.add_segment(TranscriptSegment(id="s1", text="Test", start_time=0.0, end_time=1.0))
        assert acc.state == AccumulatorState.ACCUMULATING

        acc.pause()
        assert acc.state == AccumulatorState.PAUSED

        acc.resume()
        assert acc.state == AccumulatorState.ACCUMULATING

    def test_finalize_utterance_and_clean_reset(self):
        acc = SegmentAccumulator(session_id="sess-1")
        acc.add_segment(TranscriptSegment(id="s1", text="Why is this", start_time=0.0, end_time=1.0))
        acc.add_segment(TranscriptSegment(id="s2", text="failing?", start_time=1.1, end_time=2.0))

        utterance = acc.finalize_utterance()
        assert utterance.session_id == "sess-1"
        assert utterance.full_text == "Why is this failing?"
        assert utterance.duration == 2.0
        assert utterance.is_complete is True

        # MEMORY LEAK GUARD: internal state reset
        assert acc.state == AccumulatorState.IDLE
        assert acc.count == 0

    def test_finalize_empty_accumulator(self):
        acc = SegmentAccumulator(session_id="sess-empty")
        utterance = acc.finalize_utterance()
        assert utterance.full_text == ""
        assert utterance.duration == 0.0
        assert acc.count == 0

    def test_explicit_clear(self):
        acc = SegmentAccumulator(session_id="sess-clear")
        acc.add_segment(TranscriptSegment(id="s1", text="Clear me", start_time=0.0, end_time=1.0))
        assert acc.count == 1
        acc.clear()
        assert acc.count == 0
        assert acc.state == AccumulatorState.IDLE

    def test_memory_leak_stress_test(self):
        """
        Simulate streaming 1,000 rapid segments and verify memory reset.
        Fulfills Acceptance Criteria: 'No memory leaks on large transcript sets'
        """
        acc = SegmentAccumulator(session_id="sess-stress")

        for i in range(1000):
            acc.add_segment(
                TranscriptSegment(
                    id=f"seg-{i}",
                    text=f"word{i}",
                    start_time=i * 0.1,
                    end_time=(i + 1) * 0.1,
                )
            )

        assert acc.count == 1000
        utterance = acc.finalize_utterance()
        assert len(utterance.segments) == 1000
        assert acc.count == 0
        assert acc.current_segments == []

    def test_accumulator_multiple_interims_different_timestamps(self):
        """Verify interim_text tracks advancing interim chunks with different IDs."""
        acc = SegmentAccumulator(session_id="sess-adv-interim")
        acc.add_segment(TranscriptSegment(id="chunk-1", text="Search", start_time=0.0, end_time=0.5, is_final=False))
        assert acc.interim_text == "Search"

        acc.add_segment(TranscriptSegment(id="chunk-2", text="files", start_time=0.5, end_time=1.0, is_final=False))
        # Latest interim is chunk-2
        assert acc.interim_text == "files"

        # Finalizing resolves all segments
        utt = acc.finalize_utterance()
        assert utt.full_text == "Search files"

    def test_accumulator_consecutive_pauses_and_resumes(self):
        """Verify pause/resume idempotency."""
        acc = SegmentAccumulator(session_id="sess-idempotent")
        acc.add_segment(TranscriptSegment(id="s1", text="Voice", start_time=0.0, end_time=1.0))
        assert acc.state == AccumulatorState.ACCUMULATING

        acc.pause()
        assert acc.state == AccumulatorState.PAUSED
        acc.pause()  # Redundant pause
        assert acc.state == AccumulatorState.PAUSED

        acc.resume()
        assert acc.state == AccumulatorState.ACCUMULATING
        acc.resume()  # Redundant resume
        assert acc.state == AccumulatorState.ACCUMULATING

    def test_accumulator_pause_from_idle(self):
        """Calling pause or resume while IDLE remains in IDLE."""
        acc = SegmentAccumulator(session_id="sess-idle-pause")
        assert acc.state == AccumulatorState.IDLE
        acc.pause()
        assert acc.state == AccumulatorState.IDLE
        acc.resume()
        assert acc.state == AccumulatorState.IDLE

    def test_accumulator_empty_text_segments_filtered_in_final(self):
        """Whitespace-only segments do not inject spurious spaces into full_text."""
        acc = SegmentAccumulator(session_id="sess-whitespace")
        acc.add_segment(TranscriptSegment(id="s1", text="Valid text", start_time=0.0, end_time=1.0, is_final=True))
        acc.add_segment(TranscriptSegment(id="s2", text="   ", start_time=1.0, end_time=1.5, is_final=True))
        acc.add_segment(TranscriptSegment(id="s3", text="continued", start_time=1.5, end_time=2.5, is_final=True))

        utterance = acc.finalize_utterance()
        assert utterance.full_text == "Valid text continued"

    def test_accumulator_segments_isolation_deep_copy(self):
        """Mutating current_segments does not corrupt internal accumulator buffer."""
        acc = SegmentAccumulator(session_id="sess-isolation")
        acc.add_segment(TranscriptSegment(id="s1", text="Original", start_time=0.0, end_time=1.0))

        external_list = acc.current_segments
        external_list.clear()

        # Internal buffer remains untouched
        assert acc.count == 1
        assert len(acc.current_segments) == 1


# =============================================================================
# 4. Audio Pipeline & End-to-End Integration Tests
# =============================================================================

class TestAudioPipelineIntegration:
    """Integration tests linking audio streaming frames to STT transcription and accumulation."""

    def test_audio_stream_to_accumulator_pipeline(self):
        transcriber = FakeTranscriberService()
        accumulator = SegmentAccumulator(session_id="audio-integ-001")

        audio_frame_size = 3200
        for idx in range(3):
            pcm_data = b"\x10\x00" * (audio_frame_size // 2)
            segments = transcriber.transcribe(
                audio_data=pcm_data,
                phrase_index=idx,
                start_time_offset=idx * 2.0,
            )
            assert len(segments) == 1
            accumulator.add_segment(segments[0])

        assert accumulator.count == 3
        assert accumulator.state == AccumulatorState.ACCUMULATING

        utterance = accumulator.finalize_utterance()
        assert len(utterance.segments) == 3
        assert utterance.duration >= 2.0
        assert accumulator.state == AccumulatorState.IDLE

    def test_accumulator_handles_overlapping_and_gaps(self):
        """Verify that overlapping timestamps and time gaps are properly handled."""
        accumulator = SegmentAccumulator(session_id="overlap-test")

        # Chunk 1: 0.0s -> 2.0s
        seg1 = TranscriptSegment(id="seg-1", text="First phrase", start_time=0.0, end_time=2.0, is_final=True)
        # Chunk 2 overlaps Chunk 1: 1.5s -> 3.5s
        seg2 = TranscriptSegment(id="seg-2", text="Overlapping phrase", start_time=1.5, end_time=3.5, is_final=True)
        # Chunk 3 with gap: 5.0s -> 7.0s
        seg3 = TranscriptSegment(id="seg-3", text="After gap phrase", start_time=5.0, end_time=7.0, is_final=True)

        accumulator.add_segment(seg2)
        accumulator.add_segment(seg1)
        accumulator.add_segment(seg3)

        assert [s.id for s in accumulator.current_segments] == ["seg-1", "seg-2", "seg-3"]
        utterance = accumulator.finalize_utterance()
        assert "First phrase" in utterance.full_text
        assert "Overlapping phrase" in utterance.full_text
        assert "After gap phrase" in utterance.full_text

    def test_streaming_chunks_integrated_with_accumulator(self):
        """Simulate word-by-word streaming emission fed directly into the accumulator."""
        transcriber = FakeTranscriberService()
        acc = SegmentAccumulator(session_id="stream-integ")

        chunks = transcriber.simulate_streaming_chunks(phrase_index=0)
        for chunk in chunks:
            acc.add_segment(chunk)

        utterance = acc.finalize_utterance()
        assert "error" in utterance.full_text.lower()
        assert utterance.is_complete is True
        assert acc.state == AccumulatorState.IDLE


# =============================================================================
# 5. CLI Demonstration Execution Test
# =============================================================================

def test_cli_demo_execution(capsys):
    """Verifies that the CLI demonstration runs without errors."""
    from packages.speech_to_text.cli import run_demo
    run_demo()
    captured = capsys.readouterr()
    assert "Speech-to-Text & Accumulator Demo" in captured.out
    assert "Demo Completed Successfully" in captured.out
