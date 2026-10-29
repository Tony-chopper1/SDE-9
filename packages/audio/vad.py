import struct
from packages.audio.models import AudioFrame, VADEvent, VADState


class SimpleVADDetector:
    """
    Evaluates audio frames based on RMS energy threshold.
    """
    def __init__(self, energy_threshold: float = 500.0):
        self.energy_threshold = energy_threshold

    def evaluate_frame(self, frame: AudioFrame) -> VADEvent:
        sample_count = len(frame.data) // 2
        if sample_count == 0:
            return VADEvent(
                state=VADState.SILENCE,
                timestamp=frame.timestamp,
                energy_level=0.0,
                confidence=0.99
            )

        samples = struct.unpack(f"<{sample_count}h", frame.data)
        avg_energy = sum(abs(s) for s in samples) / sample_count

        is_speech = avg_energy > self.energy_threshold
        state = VADState.SPEECH if is_speech else VADState.SILENCE

        return VADEvent(
            state=state,
            timestamp=frame.timestamp,
            energy_level=avg_energy,
            confidence=0.95 if is_speech else 0.99,
        )
