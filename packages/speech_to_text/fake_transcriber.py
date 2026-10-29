"""
Fake Transcriber Service - Starter Template
Assigned Member: Pavanchand R M (feature/speech-to-text - Task W2)
"""
from typing import List
from packages.speech_to_text.models import TranscriptSegment


class FakeTranscriberService:
    """
    Deterministic simulated STT service for offline mock testing.
    
    TODO (Pavanchand R M):
    1. Implement transcribe method to return realistic TranscriptSegment objects from audio.
    2. Support deterministic output so unit tests can assert on predictable text.
    """
    def transcribe(self, audio_data: bytes, phrase_index: int = 0) -> List[TranscriptSegment]:
        """Convert audio bytes into a list of transcript segments."""
        raise NotImplementedError("TODO: Pavanchand R M - Implement transcribe")
