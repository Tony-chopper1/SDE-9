"""
Fake Transcriber Service

Provides deterministic simulated speech-to-text transcription for local mock mode,
reproducing both single-shot transcription and streaming partial chunks with dynamic confidence scoring.
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

    def calculate_confidence(
        self,
        audio_data: bytes,
        phrase: str,
        is_final: bool = True,
    ) -> float:
        """
        Confidence Scoring Logic:
        Calculates a realistic confidence score (0.0 - 1.0) based on:
        1. Audio data completeness: Audio buffer size relative to standard 16kHz PCM (32,000 bytes/sec).
        2. Phrase linguistic complexity / word count.
        3. Interim vs. Final commitment status:
           - Interim partial chunks have confidence scaled between 0.70 and 0.92.
           - Final commitments achieve confidence between 0.94 and 0.99.
        """
        if not audio_data or len(phrase.strip()) == 0:
            return 0.0

        # Baseline confidence based on commitment status
        base_confidence = 0.95 if is_final else 0.85

        # Audio density penalty: if buffer is unusually small (<320 bytes = 10ms)
        audio_factor = 1.0 if len(audio_data) >= 320 else (len(audio_data) / 320.0)

        # Length stability factor: longer sentences have slightly more context
        word_count = len(phrase.split())
        length_bonus = min(0.04, word_count * 0.005)

        raw_score = (base_confidence + length_bonus) * audio_factor
        # Clamp to [0.0, 1.0] and round to 2 decimals
        return round(min(1.0, max(0.0, raw_score)), 2)

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

        confidence = self.calculate_confidence(audio_data, phrase, is_final=True)

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

        # Dummy audio payload for confidence scoring simulation
        simulated_audio = b"\x00" * 3200

        for idx, word in enumerate(words):
            accumulated_words.append(word)
            is_last = idx == len(words) - 1
            t_start = round(base_time + (idx * 0.3), 3)
            t_end = round(t_start + 0.3, 3)

            current_text = " ".join(accumulated_words)
            confidence = self.calculate_confidence(
                simulated_audio,
                current_text,
                is_final=is_last,
            )

            segments.append(
                TranscriptSegment(
                    id=f"stream-seg-{idx}",
                    text=current_text,
                    confidence=confidence,
                    start_time=t_start,
                    end_time=t_end,
                    is_final=is_last,
                    language=self.default_language,
                )
            )

        return segments
