"""
Voice Activity Detection (VAD) interfaces and implementations.
Owner: Satwik A (feature/audio-vad)

Provides:
- BaseVAD: Provider-independent abstract base class.
- MockVAD: Deterministic, scripted or energy-inferred mock VAD for testing.
- EnergyVAD: Lightweight, deterministic RMS dBFS energy detector with hangover smoothing and trigger confirmation.
- SimpleVADDetector: Team starter interface evaluating frames against an RMS amplitude threshold and tracking VADState transitions.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from packages.audio.exceptions import VADError
from packages.audio.models import AudioFrame, VADEvent, VADResult, VADState


class BaseVAD(ABC):
    """Abstract, provider-independent Voice Activity Detector interface."""

    @abstractmethod
    def process_frame(self, frame: AudioFrame) -> VADResult:
        """Analyze an audio frame and return a VAD classification result.

        Args:
            frame: Input AudioFrame instance.

        Returns:
            VADResult containing speech classification flag, confidence, and dBFS level.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset internal temporal states and smoothing buffers."""
        pass


class MockVAD(BaseVAD):
    """Deterministic mock Voice Activity Detector for testing and simulation.

    Supports either:
    1. Pre-scripted boolean sequences (e.g. [True, True, False, ...]).
    2. Automatic thresholding based on frame dBFS energy calculation.
    """

    def __init__(
        self,
        scripted_decisions: Optional[List[bool]] = None,
        default_speech: bool = False,
        fixed_confidence: float = 0.95,
        energy_threshold_db: float = -45.0,
    ):
        self.scripted_decisions = list(scripted_decisions) if scripted_decisions is not None else None
        self.default_speech = default_speech
        self.fixed_confidence = fixed_confidence
        self.energy_threshold_db = energy_threshold_db

        self._frame_index = 0
        self._speech_count = 0

    def reset(self) -> None:
        """Reset frame counter and speech statistics."""
        self._frame_index = 0
        self._speech_count = 0

    @property
    def frames_processed(self) -> int:
        return self._frame_index

    @property
    def speech_frames_detected(self) -> int:
        return self._speech_count

    def process_frame(self, frame: AudioFrame) -> VADResult:
        if not isinstance(frame, AudioFrame):
            raise VADError(f"Expected AudioFrame instance, got {type(frame).__name__}")

        energy_db = frame.calculate_dbfs()

        if self.scripted_decisions is not None:
            if self._frame_index < len(self.scripted_decisions):
                is_speech = self.scripted_decisions[self._frame_index]
            else:
                is_speech = self.default_speech
        else:
            is_speech = energy_db > self.energy_threshold_db

        if is_speech:
            self._speech_count += 1

        self._frame_index += 1

        return VADResult(
            is_speech=is_speech,
            confidence=self.fixed_confidence if is_speech else 0.1,
            energy_db=energy_db,
            metadata={
                "engine": "MockVAD",
                "frame_index": self._frame_index,
                "scripted": self.scripted_decisions is not None,
            },
        )


class EnergyVAD(BaseVAD):
    """Deterministic, zero-dependency RMS energy-based Voice Activity Detector.

    Operates in the decibels relative to full scale (dBFS) domain:
    - Computes RMS and converts to dBFS from actual 16-bit PCM samples.
    - Configurable speech activation threshold (threshold_db).
    - Trigger confirmation (trigger_frames): requires N consecutive active frames before transitioning to speech.
    - Hangover smoothing (hangover_frames): holds speech state for N frames after energy drops to prevent word clipping.
    """

    def __init__(
        self,
        threshold_db: float = -42.0,
        hangover_frames: int = 3,
        trigger_frames: int = 2,
    ):
        """Initialize EnergyVAD.

        Args:
            threshold_db: Energy in dBFS above which a frame is active (default: -42.0 dBFS).
            hangover_frames: Number of frames to hold speech state after energy drops (default: 3).
            trigger_frames: Number of consecutive active frames required to trigger speech (default: 2).
        """
        self.threshold_db = threshold_db
        self.hangover_frames = hangover_frames
        self.trigger_frames = trigger_frames

        self._is_in_speech = False
        self._consecutive_active_frames = 0
        self._hangover_counter = 0
        self._total_frames = 0

    def reset(self) -> None:
        """Reset internal temporal smoothing state."""
        self._is_in_speech = False
        self._consecutive_active_frames = 0
        self._hangover_counter = 0
        self._total_frames = 0

    @property
    def is_speech_active(self) -> bool:
        """Current smoothed speech state."""
        return self._is_in_speech

    def process_frame(self, frame: AudioFrame) -> VADResult:
        """Process one audio frame and apply temporal smoothing."""
        if not isinstance(frame, AudioFrame):
            raise VADError(f"Expected AudioFrame instance, got {type(frame).__name__}")

        self._total_frames += 1
        energy_db = frame.calculate_dbfs()
        frame_above_threshold = energy_db >= self.threshold_db

        # Trigger confirmation logic
        if frame_above_threshold:
            self._consecutive_active_frames += 1
            if self._consecutive_active_frames >= self.trigger_frames:
                self._is_in_speech = True
                self._hangover_counter = self.hangover_frames
        else:
            self._consecutive_active_frames = 0
            if self._hangover_counter > 0:
                self._hangover_counter -= 1
            else:
                self._is_in_speech = False

        # Continuous confidence estimate based on margin relative to threshold
        margin = energy_db - self.threshold_db
        if self._is_in_speech:
            confidence = min(1.0, max(0.5, 0.5 + (margin / 30.0)))
        else:
            confidence = max(0.0, min(0.49, 0.5 + (margin / 30.0)))

        return VADResult(
            is_speech=self._is_in_speech,
            confidence=round(confidence, 4),
            energy_db=round(energy_db, 2),
            metadata={
                "engine": "EnergyVAD",
                "frame_raw_active": frame_above_threshold,
                "hangover_remaining": self._hangover_counter,
                "consecutive_active": self._consecutive_active_frames,
                "total_frames": self._total_frames,
            },
        )


class SimpleVADDetector:
    """Team starter interface: evaluates frames against a linear RMS amplitude threshold.

    Distinction Note:
        - SimpleVADDetector uses linear RMS amplitude threshold (default: 500.0, scale 0 to 32767).
        - EnergyVAD uses logarithmic dBFS threshold (default: -42.0 dBFS, scale -100 to 0).

    Transitions tracked:
        - SILENCE: Prior silent, current below threshold.
        - SPEECH_START: Prior silent, current reaches or exceeds threshold.
        - SPEECH: Prior in speech, current remains at or above threshold.
        - SPEECH_END: Prior in speech, current drops below threshold.
    """

    def __init__(self, energy_threshold: float = 500.0):
        self.energy_threshold = energy_threshold
        self._in_speech = False

    def reset(self) -> None:
        """Reset state tracking."""
        self._in_speech = False

    def evaluate_frame(self, frame: AudioFrame) -> VADEvent:
        """Evaluate an AudioFrame from raw PCM samples and return a VADEvent."""
        if not isinstance(frame, AudioFrame):
            raise VADError(f"Expected AudioFrame instance, got {type(frame).__name__}")

        rms = frame.calculate_rms()
        is_above = (rms >= self.energy_threshold)

        if is_above:
            if not self._in_speech:
                state = VADState.SPEECH_START
                self._in_speech = True
            else:
                state = VADState.SPEECH
            confidence = min(1.0, max(0.5, 0.5 + ((rms - self.energy_threshold) / (self.energy_threshold * 2 + 1e-5))))
        else:
            if self._in_speech:
                state = VADState.SPEECH_END
                self._in_speech = False
            else:
                state = VADState.SILENCE
            confidence = max(0.0, min(0.49, 0.5 - ((self.energy_threshold - rms) / (self.energy_threshold * 2 + 1e-5))))

        return VADEvent(
            state=state,
            timestamp=frame.timestamp,
            energy_level=round(rms, 2),
            confidence=round(confidence, 4),
            frame_index=frame.frame_index,
            timestamp_ms=frame.timestamp_ms,
        )


__all__ = [
    "BaseVAD",
    "MockVAD",
    "EnergyVAD",
    "SimpleVADDetector",
]
