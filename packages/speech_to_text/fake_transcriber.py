"""
Fake Transcriber Service
Owner: Pavanchand R M (feature/speech-to-text - Team Lead)
Task ID: W2

Provides deterministic simulated speech-to-text transcription for local mock mode,
reproducing both single-shot transcription and streaming partial chunks.
"""
import time
from typing import List
from packages.speech_to_text.models import TranscriptSegment


class FakeTranscriberService:
    """
    Deterministic simulated STT service.
    Maps to official PRD use cases (UC-01 to UC-08).
    """

    MOCK_PHRASES = [
        "Why is this application showing an error?",                     # UC-02 Error Analysis
        "Find my project report and summarize it.",                      # UC-07 Multi-Step Task
        "Move these files into the project folder.",                     # UC-08 Controlled Action
        "What am I currently looking at on the screen?",                 # UC-01 Screen Query
        "Explain the methodology shown on this page.",                   # UC-03 Document Explanation
        "Search for the latest benchmark results in our codebase.",       # UC-05 Research
    ]

    def __init__(self, default_language: str = "en"):
        self.default_language = default_language

    def transcribe(
        self,
        audio_data: bytes,
        phrase_index: int = 0,
        start_time_offset: float = 0.0,
    ) -> List[TranscriptSegment]:
        """
        Converts simulated audio bytes into a final TranscriptSegment.
        """
        if not audio_data:
            return []

        phrase = self.MOCK_PHRASES[phrase_index % len(self.MOCK_PHRASES)]
        base_time = start_time_offset if start_time_offset > 0 else time.time()
        duration = max(0.5, len(phrase) * 0.05)  # estimate ~50ms per character

        # Higher confidence for non-empty audio
        confidence = 0.96 if len(audio_data) >= 100 else 0.85

        segment = TranscriptSegment(
            id=f"seg-{int(base_time * 1000)}",
            text=phrase,
            confidence=confidence,
            start_time=round(base_time, 3),
            end_time=round(base_time + duration, 3),
            is_final=True,
            language=self.default_language,
        )
        return [segment]

    def simulate_streaming_chunks(
        self,
        phrase_index: int = 0,
        start_time_offset: float = 0.0,
    ) -> List[TranscriptSegment]:
        """
        Simulates word-by-word streaming STT.
        Emits interim partial segments followed by a final segment.
        """
        full_phrase = self.MOCK_PHRASES[phrase_index % len(self.MOCK_PHRASES)]
        words = full_phrase.split()
        segments: List[TranscriptSegment] = []

        base_time = start_time_offset if start_time_offset > 0 else time.time()
        accumulated_words: List[str] = []

        for idx, word in enumerate(words):
            accumulated_words.append(word)
            is_last = idx == len(words) - 1
            t_start = round(base_time + (idx * 0.3), 3)
            t_end = round(t_start + 0.3, 3)

            segments.append(
                TranscriptSegment(
                    id=f"stream-seg-{idx}",
                    text=" ".join(accumulated_words),
                    confidence=0.92 if not is_last else 0.98,
                    start_time=t_start,
                    end_time=t_end,
                    is_final=is_last,
                    language=self.default_language,
                )
            )

        return segments
