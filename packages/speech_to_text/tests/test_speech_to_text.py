"""
Comprehensive Unit & Integration Tests for Speech-to-Text Module
"""
import os
import pytest
from packages.speech_to_text.models import (
    AccumulatorState,
    TranscriptSegment,
    AccumulatedUtterance,
    TranscriptEvent,
)
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.accumulator import SegmentAccumulator


class TestTranscriptModels:
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

    def test_transcript_segment_confidence_bounds(self):
        # Confidence must be between 0.0 and 1.0
        with pytest.raises(ValueError):
            TranscriptSegment(
                id="seg-err",
                text="error",
                confidence=1.5,
                start_time=0.0,
                end_time=1.0,
            )

        with pytest.raises(ValueError):
            TranscriptSegment(
                id="seg-err-neg",
                text="error",
                confidence=-0.1,
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


class TestFakeTranscriberService:
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

    def test_transcribe_with_custom_timestamp(self):
        service = FakeTranscriberService()
        fixed_time = 1000.0
        res = service.transcribe(b"\x00" * 1000, phrase_index=2, start_time_offset=fixed_time)
        assert res[0].start_time == fixed_time
        assert res[0].end_time > fixed_time

    def test_simulate_streaming_chunks(self):
        service = FakeTranscriberService()
        chunks = service.simulate_streaming_chunks(phrase_index=0, start_time_offset=5.0)

        assert len(chunks) > 1
        # Intermediary chunks should be partial (is_final=False)
        assert chunks[0].is_final is False
        # Last chunk should be final (is_final=True)
        assert chunks[-1].is_final is True
        assert "error" in chunks[-1].text.lower()


class TestSegmentAccumulator:
    def test_initial_state_is_idle(self):
        acc = SegmentAccumulator(session_id="sess-1")
        assert acc.state == AccumulatorState.IDLE
        assert acc.count == 0

    def test_chronological_ordering_of_out_of_order_chunks(self):
        acc = SegmentAccumulator(session_id="sess-1")

        seg_second = TranscriptSegment(
            id="s2",
            text="world",
            start_time=1.1,
            end_time=2.0,
        )
        seg_first = TranscriptSegment(
            id="s1",
            text="Hello",
            start_time=0.0,
            end_time=1.0,
        )

        # Add second segment first, then first segment
        acc.add_segment(seg_second)
        acc.add_segment(seg_first)

        ordered = acc.current_segments
        assert ordered[0].text == "Hello"
        assert ordered[1].text == "world"

    def test_interim_segment_update_overwriting(self):
        acc = SegmentAccumulator(session_id="sess-1")

        # Streaming interim partial
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

        # Count should remain 1 (overwritten, not duplicated)
        assert acc.count == 1
        assert acc.current_segments[0].text == "Why is this application"
        assert acc.current_segments[0].is_final is True

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

        # Finalize and verify immediate memory reclamation
        utterance = acc.finalize_utterance()
        assert len(utterance.segments) == 1000
        assert acc.count == 0
        assert acc.current_segments == []


class TestAudioPipelineIntegration:
    """
    Integration tests linking audio streaming frames to STT transcription and segment accumulation.
    Fulfills Day 3-4 and Day 5-6 ClickUp requirements:
    - 'Integrate with audio pipeline'
    - 'Integration tests with audio/accumulator'
    - 'Edge case testing (overlaps, gaps)'
    """
    def test_audio_stream_to_accumulator_pipeline(self):
        transcriber = FakeTranscriberService()
        accumulator = SegmentAccumulator(session_id="audio-integ-001")

        # Simulate continuous audio chunks (e.g. 100ms PCM frames at 16kHz)
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
        """
        Verify that overlapping timestamps and time gaps are properly handled.
        Fulfills Acceptance Criteria: 'Accumulator handles overlapping timestamps'
        """
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


def test_cli_demo_execution(capsys):
    """Verifies that the CLI demonstration runs without errors."""
    from packages.speech_to_text.cli import run_demo
    run_demo()
    captured = capsys.readouterr()
    assert "Speech-to-Text & Accumulator Demo" in captured.out
    assert "Demo Completed Successfully" in captured.out

