"""
Unit Tests for Speech-to-Text Module
Assigned Member: Pavanchand R M (feature/speech-to-text - Task W2)

TODO (Pavanchand R M):
Write unit tests for FakeTranscriberService and SegmentAccumulator to achieve >80% coverage.
"""
import pytest
from packages.speech_to_text import TranscriptSegment, AccumulatedUtterance, FakeTranscriberService, SegmentAccumulator


def test_transcript_model_instantiation():
    """Verify that TranscriptSegment and AccumulatedUtterance can be constructed."""
    seg = TranscriptSegment(
        id="seg-1",
        text="Hello world",
        confidence=0.95,
        start_time=0.0,
        end_time=1.0,
    )
    assert seg.text == "Hello world"
    assert seg.confidence == 0.95


# TODO (Pavanchand R M): Uncomment and implement after completing fake_transcriber.py and accumulator.py
# def test_fake_transcriber_returns_segments():
#     stt = FakeTranscriberService()
#     segments = stt.transcribe(b"dummy_pcm")
#     assert len(segments) > 0
#
# def test_segment_accumulator_ordering_and_reset():
#     acc = SegmentAccumulator("sess-1")
#     ...
