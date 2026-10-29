import random
import time
from typing import List
from packages.speech_to_text.models import TranscriptSegment


class FakeTranscriberService:
    """
    Deterministic simulated speech-to-text service for local mock testing.
    """
    MOCK_PHRASES = [
        "Why is this application showing an error?",
        "Find my project report and summarize it.",
        "Move these files into the project folder.",
        "What am I currently looking at on the screen?",
        "Explain the methodology shown on this page.",
    ]

    def transcribe(self, audio_data: bytes, phrase_index: int = 0) -> List[TranscriptSegment]:
        chosen_phrase = self.MOCK_PHRASES[phrase_index % len(self.MOCK_PHRASES)]
        timestamp = time.time()
        return [
            TranscriptSegment(
                id=f"seg-{int(timestamp * 1000)}",
                text=chosen_phrase,
                confidence=0.98,
                start_time=timestamp,
                end_time=timestamp + 1.5,
                is_final=True,
            )
        ]
