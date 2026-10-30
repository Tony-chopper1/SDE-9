"""
Voice Activity Detection (VAD) - Starter Template
Assigned Member: Satwik A (feature/audio-vad - Task W1)
"""
from packages.audio.models import AudioFrame, VADEvent, VADState


class SimpleVADDetector:
    """
    Evaluates audio frames to classify speech vs silence.
    
    TODO (Satwik A):
    1. Read 16-bit PCM samples from frame.data.
    2. Compute energy level (e.g. RMS or average absolute amplitude).
    3. Return VADEvent with state VADState.SPEECH if energy > threshold, else VADState.SILENCE.
    """
    def __init__(self, energy_threshold: float = 500.0):
        self.energy_threshold = energy_threshold

    def evaluate_frame(self, frame: AudioFrame) -> VADEvent:
        """Evaluate an AudioFrame and return a VADEvent."""
        raise NotImplementedError("TODO: Satwik A - Implement evaluate_frame")
