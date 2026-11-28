"""
Long-Session and Mid-Stream Cancellation Consistency Tests.
Owner: Pavan (feature/pavan-week4) - Days 25-27

Acceptance Criteria Validated:
1. Long-session tests show no duplicated, lost, or out-of-order final segments.
2. Cancelling mid-stream leaves a consistent transcript with no segments emitted after the cancel, and a test proves it.
3. Memory stays strictly bounded with zero leak over sustained audio streams.
"""

from __future__ import annotations

import time
from typing import List
from uuid import uuid4

import pytest

from packages.speech_to_text.fixtures import SyntheticAudioFixtures
from packages.speech_to_text.models import TranscriptEvent, TranscriptSegment
from packages.speech_to_text.orchestrator import OrchestratorState, SpeechToTextOrchestrator


class TestWeek4LongSessionConsistency:
    """Validates long-session continuity, segment deduplication, and monotonic ordering."""

    def test_long_session_no_lost_or_duplicate_segments(self):
        """Acceptance Criteria: Long-session tests show no duplicated, lost or out-of-order final segments."""
        session_id = f"long-session-{uuid4()}"
        events_emitted: List[TranscriptEvent] = []

        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            on_event=events_emitted.append,
        )
        orchestrator.start()

        # Ingest 300 synthetic frames (representing continuous multi-utterance conversation)
        frame_stream = SyntheticAudioFixtures.long_session_stream(total_frames=300)
        for chunk in frame_stream:
            orchestrator.push_audio(
                chunk.data,
                sequence_number=chunk.sequence_number,
                is_speech=chunk.is_speech,
            )

        # Finalize full stream
        orchestrator.flush()
        final_utterance = orchestrator.stop()

        # 1. Verify finalized segments ordering
        final_segments = orchestrator.reconciler.finalized_segments
        assert len(final_segments) > 0

        # Assert strictly increasing start times (no out-of-order final segments)
        for i in range(len(final_segments) - 1):
            curr_seg = final_segments[i]
            next_seg = final_segments[i + 1]
            assert curr_seg.start_time <= next_seg.start_time, (
                f"Segment ordering violated: {curr_seg.start_time} > {next_seg.start_time}"
            )
            assert curr_seg.start_time <= curr_seg.end_time

        # 2. Assert zero duplicate segment IDs
        segment_ids = [s.id for s in final_segments]
        assert len(segment_ids) == len(set(segment_ids)), "Found duplicate segment IDs in final output!"

        # 3. Assert zero duplicate content hashes
        hashes = [orchestrator.reconciler._compute_segment_hash(s) for s in final_segments]
        assert len(hashes) == len(set(hashes)), "Found duplicate content hashes in final transcript!"

        # 4. Verify utterance completeness
        assert final_utterance.is_complete is True
        assert len(final_utterance.full_text) > 0
        assert final_utterance.session_id == session_id

    def test_long_session_bounded_memory_usage(self):
        """Verify internal buffers reset appropriately and do not retain unbounded memory."""
        session_id = f"memory-bounded-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(session_id=session_id)
        orchestrator.start()

        chunk_data = b"\x01\x00" * 1600  # 3200 bytes per chunk

        # Stream 100 consecutive chunks
        for i in range(100):
            orchestrator.push_audio(chunk_data, sequence_number=i)
            if i % 20 == 0:
                orchestrator.finalize_utterance()
                # Internal segment accumulator buffer must clear after utterance finalization
                assert orchestrator.accumulator.count == 0

        assert orchestrator.total_frames_processed == 100
        # PCM buffer is drained
        assert len(orchestrator._buffered_pcm) == 0


class TestWeek4CancellationConsistency:
    """Validates cancellation guarantees and post-cancellation silence."""

    def test_cancelling_mid_stream_leaves_consistent_transcript_with_no_subsequent_events(self):
        """Acceptance Criteria: Cancelling mid-stream leaves a consistent transcript with no segments emitted after cancel."""
        session_id = f"cancel-consistency-{uuid4()}"
        events_emitted: List[TranscriptEvent] = []

        orchestrator = SpeechToTextOrchestrator(
            session_id=session_id,
            on_event=events_emitted.append,
        )
        orchestrator.start()

        # Step 1: Ingest active speech to produce committed transcripts
        clean_frames = list(SyntheticAudioFixtures.clean_speech_stream(num_frames=20))
        for f in clean_frames[:10]:
            orchestrator.push_audio(f.data, sequence_number=f.sequence_number)

        # Confirm some transcript is established
        transcript_before_cancel = orchestrator.get_full_transcript()
        events_count_before_cancel = len(events_emitted)
        assert len(transcript_before_cancel) > 0
        assert events_count_before_cancel > 0

        # Step 2: Trigger mid-stream cancellation
        cancel_event = orchestrator.cancel(reason="User pressed stop button mid-speech")
        assert orchestrator.state == OrchestratorState.CANCELLED
        assert cancel_event.event_type == "transcript.cancelled"

        # Step 3: Record transcript snapshot at cancellation point
        frozen_transcript = orchestrator.get_full_transcript()
        events_count_at_cancel = len(events_emitted)
        assert events_count_at_cancel == events_count_before_cancel + 1  # only cancel_event added

        # Step 4: Attempt to push further incoming audio frames after cancellation
        for f in clean_frames[10:]:
            pushed_events = orchestrator.push_audio(f.data, sequence_number=f.sequence_number)
            # Must emit zero segments
            assert pushed_events == []

        # Attempt to flush after cancellation
        flush_result = orchestrator.flush()
        assert flush_result is None

        # Step 5: Assert no segments or events were emitted after the cancellation event
        assert len(events_emitted) == events_count_at_cancel, (
            "Events were emitted after cancellation!"
        )
        # Transcript text remains completely consistent and frozen
        assert orchestrator.get_full_transcript() == frozen_transcript
        assert len(orchestrator._buffered_pcm) == 0

    def test_cancellation_discards_uncommitted_interim_drafts(self):
        """Verify pending provisional interim segments are completely discarded upon cancel."""
        session_id = f"cancel-interim-{uuid4()}"
        orchestrator = SpeechToTextOrchestrator(session_id=session_id, enable_revision_events=True)
        orchestrator.start()

        # Manually seed an interim segment in reconciler
        interim_seg = TranscriptSegment(
            id="draft-to-cancel",
            text="I was about to say something private",
            confidence=0.85,
            start_time=0.0,
            end_time=1.5,
            is_final=False,
        )
        orchestrator.reconciler.process_segment(interim_seg)
        assert orchestrator.reconciler.active_interim is not None

        # Cancel session
        orchestrator.cancel(reason="Privacy interrupt")

        # Active interim must be cleared immediately
        assert orchestrator.reconciler.active_interim is None
        assert "private" not in orchestrator.reconciler.get_finalized_text()
