"""
Segment Accumulator - Starter Template
Assigned Member: Pavanchand R M (feature/speech-to-text - Task W2)
"""
from typing import List
from packages.speech_to_text.models import TranscriptSegment, AccumulatedUtterance


class SegmentAccumulator:
    """
    State machine for aggregating streaming partial/final transcript chunks.
    
    TODO (Pavanchand R M):
    1. Maintain an internal list of TranscriptSegment items for session_id.
    2. Overwrite interim segments if same ID is received; otherwise append.
    3. Ensure segments are ordered chronologically by start_time.
    4. Implement finalize_utterance() to combine text into a complete sentence and clear state.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._segments: List[TranscriptSegment] = []

    def add_segment(self, segment: TranscriptSegment) -> None:
        """Add or update a streaming transcript segment."""
        raise NotImplementedError("TODO: Pavanchand R M - Implement add_segment")

    def finalize_utterance(self) -> AccumulatedUtterance:
        """Combine accumulated segments into a complete utterance and reset accumulator."""
        raise NotImplementedError("TODO: Pavanchand R M - Implement finalize_utterance")
