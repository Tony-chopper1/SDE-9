import time
from typing import List
from packages.speech_to_text.models import TranscriptSegment, AccumulatedUtterance


class SegmentAccumulator:
    """
    State machine for aggregating streaming partial/final transcript chunks.
    Resolves overlapping timestamps, orders chronologically, and cleans up memory.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._segments: List[TranscriptSegment] = []
        self._utterance_id = f"utt-{int(time.time() * 1000)}"

    def add_segment(self, segment: TranscriptSegment) -> None:
        # Overwrite if matching segment ID exists, otherwise insert
        existing_idx = next((i for i, s in enumerate(self._segments) if s.id == segment.id), None)
        if existing_idx is not None:
            self._segments[existing_idx] = segment
        else:
            self._segments.append(segment)

        # Sort chronologically
        self._segments.sort(key=lambda s: s.start_time)

    def finalize_utterance(self) -> AccumulatedUtterance:
        full_text = " ".join(s.text.strip() for s in self._segments if s.text.strip())
        start_time = self._segments[0].start_time if self._segments else time.time()
        end_time = self._segments[-1].end_time if self._segments else time.time()

        utterance = AccumulatedUtterance(
            id=self._utterance_id,
            session_id=self.session_id,
            full_text=full_text,
            segments=list(self._segments),
            start_time=start_time,
            end_time=end_time,
            is_complete=True,
        )

        # Reset to prevent memory leaks across sessions
        self._segments.clear()
        self._utterance_id = f"utt-{int(time.time() * 1000)}"

        return utterance

    @property
    def current_segments_count(self) -> int:
        return len(self._segments)
