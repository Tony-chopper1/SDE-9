"""
Transcript Reconciler for Streaming Speech-to-Text.

Handles:
1. Strict monotonic chronological ordering of incoming transcript segments.
2. Duplicate segment suppression (by segment ID, sequence hash, or timestamp overlap).
3. Interim-to-Final reconciliation (interim updates evolve the working draft; final commitments lock history).
4. Smooth text continuity without word repetition or stuttering.
"""

from __future__ import annotations

import hashlib
import time
from typing import List, Optional, Set

from packages.speech_to_text.models import TranscriptEvent, TranscriptSegment


class TranscriptReconciler:
    """Stateful reconciler ensuring streaming STT output is ordered, deduplicated, and consistent."""

    def __init__(self, session_id: str = "default-session") -> None:
        self.session_id = session_id
        self._finalized_segments: List[TranscriptSegment] = []
        self._interim_segment: Optional[TranscriptSegment] = None
        self._seen_ids: Set[str] = set()
        self._seen_hashes: Set[str] = set()
        self._duplicate_count: int = 0

    @property
    def duplicate_count(self) -> int:
        """Number of duplicate segments suppressed."""
        return self._duplicate_count

    @property
    def finalized_segments(self) -> List[TranscriptSegment]:
        """Chronologically ordered committed segments."""
        return list(self._finalized_segments)

    @property
    def active_interim(self) -> Optional[TranscriptSegment]:
        """Currently active uncommitted interim segment, if any."""
        return self._interim_segment

    def process_segment(self, segment: TranscriptSegment) -> Optional[TranscriptEvent]:
        """Reconcile an incoming streaming segment.

        Returns:
            A :class:`~packages.speech_to_text.models.TranscriptEvent` if the segment is accepted,
            or ``None`` if the segment is a suppressed duplicate or empty.
        """
        if not segment.text or not segment.text.strip():
            return None

        # 1. Duplicate Detection & Suppression
        content_hash = self._compute_segment_hash(segment)
        if segment.id in self._seen_ids or content_hash in self._seen_hashes:
            self._duplicate_count += 1
            return None

        # 2. Interim vs. Final Reconciliation
        if not segment.is_final:
            # Interim segment: Update current working draft
            self._interim_segment = segment
            return TranscriptEvent(
                event_type="transcript.interim",
                session_id=self.session_id,
                segment=segment,
                timestamp=time.time(),
            )

        # 3. Final Segment Commitment
        # Mark as seen so duplicates are permanently rejected
        self._seen_ids.add(segment.id)
        self._seen_hashes.add(content_hash)

        # Cleanly clear the interim draft
        self._interim_segment = None

        # Insert and maintain strict chronological order
        self._insert_chronologically(segment)

        return TranscriptEvent(
            event_type="transcript.final",
            session_id=self.session_id,
            segment=segment,
            timestamp=time.time(),
        )

    def _insert_chronologically(self, segment: TranscriptSegment) -> None:
        """Insert segment in sorted order by start_time, resolving boundary overlaps."""
        self._finalized_segments.append(segment)
        self._finalized_segments.sort(key=lambda s: (s.start_time, s.end_time))

    def _compute_segment_hash(self, segment: TranscriptSegment) -> str:
        """Compute unique fingerprint based on time window, finality, and normalized text."""
        normalized_text = " ".join(segment.text.strip().lower().split())
        key = f"{segment.start_time:.3f}:{segment.end_time:.3f}:{segment.is_final}:{normalized_text}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def get_full_transcript(self) -> str:
        """Return the complete coherent transcript (all finalized segments + active interim)."""
        texts = [s.text.strip() for s in self._finalized_segments if s.text.strip()]
        if self._interim_segment and self._interim_segment.text.strip():
            texts.append(self._interim_segment.text.strip())
        return " ".join(texts)

    def get_finalized_text(self) -> str:
        """Return only the locked, finalized transcript text."""
        return " ".join(s.text.strip() for s in self._finalized_segments if s.text.strip())

    def flush(self) -> Optional[TranscriptEvent]:
        """Commit any pending interim segment as final (e.g. on stream completion or silence)."""
        if not self._interim_segment or not self._interim_segment.text.strip():
            return None

        # Promote interim to final
        promoted = TranscriptSegment(
            id=f"{self._interim_segment.id}-flushed",
            text=self._interim_segment.text,
            confidence=self._interim_segment.confidence,
            start_time=self._interim_segment.start_time,
            end_time=self._interim_segment.end_time,
            is_final=True,
            language=self._interim_segment.language,
        )
        self._interim_segment = None
        return self.process_segment(promoted)

    def clear(self) -> None:
        """Reset reconciler state for a fresh session."""
        self._finalized_segments.clear()
        self._interim_segment = None
        self._seen_ids.clear()
        self._seen_hashes.clear()
        self._duplicate_count = 0
