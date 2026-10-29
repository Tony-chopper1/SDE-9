from packages.speech_to_text import FakeTranscriberService, SegmentAccumulator, TranscriptSegment


def test_fake_transcriber_returns_segments():
    stt = FakeTranscriberService()
    segments = stt.transcribe(b"dummy_pcm_bytes", phrase_index=0)

    assert len(segments) == 1
    assert "error" in segments[0].text
    assert segments[0].confidence > 0.9


def test_segment_accumulator_ordering_and_reset():
    accumulator = SegmentAccumulator(session_id="session-test")

    seg1 = TranscriptSegment(
        id="s1",
        text="Why is",
        confidence=0.95,
        start_time=1.0,
        end_time=1.5,
    )
    seg2 = TranscriptSegment(
        id="s2",
        text="this error appearing?",
        confidence=0.98,
        start_time=1.6,
        end_time=2.4,
    )

    accumulator.add_segment(seg1)
    accumulator.add_segment(seg2)
    assert accumulator.current_segments_count == 2

    utterance = accumulator.finalize_utterance()
    assert utterance.full_text == "Why is this error appearing?"
    assert utterance.is_complete is True
    # Memory leak guard: should be clean
    assert accumulator.current_segments_count == 0
