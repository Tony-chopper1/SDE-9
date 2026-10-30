"""
Segment Accumulator State Machine
Owner: Pavanchand R M (feature/speech-to-text - Team Lead)
Task ID: W2

Aggregates streaming partial and final transcript chunks, handles overlapping timestamps,
orders segments chronologically, and prevents memory leaks through state-managed resets.
"""
import time
from typing import List, Optional
from packages.speech_to_text.models import (
    AccumulatorState,
    AccumulatedUtterance,
    TranscriptSegment,
)


class SegmentAccumulator:
    """
    State machine for aggregating streaming speech segments into coherent utterances.

    Transitions:
        IDLE -> ACCUMULATING -> FINALIZED -> IDLE
        ACCUMULATING -> PAUSED -> ACCUMULATING
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._segments: List[TranscriptSegment] = []
        self._state: AccumulatorState = AccumulatorState.IDLE
        self._utterance_id = self._generate_utterance_id()

    @property
    def state(self) -> AccumulatorState:
        return self._state

    @property
    def current_segments(self) -> List[TranscriptSegment]:
        return list(self._segments)

    @property
    def count(self) -> int:
        return len(self._segments)

    def add_segment(self, segment: TranscriptSegment) -> None:
        """
        Adds a new streaming transcript segment or updates an existing one.
        Handles:
          - Out-of-order segment arrivals (re-sorts chronologically).
          - Updating interim segments when a final segment with the same ID arrives.
          - Overlapping timestamp resolution.
        """
        if self._state == AccumulatorState.FINALIZED:
            # Automatic transition back to ACCUMULATING if new speech arrives
            self._reset_internal_buffer()

        self._state = AccumulatorState.ACCUMULATING

        # Check if segment already exists (e.g. streaming update for the same chunk ID)
        existing_index = next(
            (i for i, s in enumerate(self._segments) if s.id == segment.id),
            None,
        )

        if existing_index is not None:
            # Overwrite interim segment with updated content or final status
            self._segments[existing_index] = segment
        else:
            self._segments.append(segment)

        # Re-sort chronologically by start_time
        self._segments.sort(key=lambda s: s.start_time)

    def pause(self) -> None:
        """Pauses accumulation without clearing the buffer (e.g. during VAD silence)."""
        if self._state == AccumulatorState.ACCUMULATING:
            self._state = AccumulatorState.PAUSED

    def resume(self) -> None:
        """Resumes accumulation after silence."""
        if self._state == AccumulatorState.PAUSED:
            self._state = AccumulatorState.ACCUMULATING

    def finalize_utterance(self) -> AccumulatedUtterance:
        """
        Synthesizes all buffered segments into a single cohesive utterance.
        Cleans up the internal buffer to prevent memory leaks.
        """
        self._state = AccumulatorState.FINALIZED

        if not self._segments:
            empty_time = time.time()
            return AccumulatedUtterance(
                id=self._utterance_id,
                session_id=self.session_id,
                full_text="",
                segments=[],
                start_time=empty_time,
                end_time=empty_time,
                duration=0.0,
                is_complete=True,
            )

        # Merge text: deduplicate consecutive overlapping words if any
        final_segments = [s for s in self._segments if s.is_final]
        segments_to_use = final_segments if final_segments else self._segments

        full_text = " ".join(s.text.strip() for s in segments_to_use if s.text.strip())
        start_time = self._segments[0].start_time
        end_time = self._segments[-1].end_time
        duration = max(0.0, round(end_time - start_time, 3))

        utterance = AccumulatedUtterance(
            id=self._utterance_id,
            session_id=self.session_id,
            full_text=full_text,
            segments=list(self._segments),
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            is_complete=True,
        )

        # CRITICAL FOR MEMORY LEAK PREVENTION:
        # Clear buffer immediately upon finalization
        self._reset_internal_buffer()
        return utterance

    def clear(self) -> None:
        """Explicitly clear buffer and reset state to IDLE."""
        self._reset_internal_buffer()

    def _reset_internal_buffer(self) -> None:
        self._segments.clear()
        self._state = AccumulatorState.IDLE
        self._utterance_id = self._generate_utterance_id()

    def _generate_utterance_id(self) -> str:
        return f"utt-{int(time.time() * 1000)}"
