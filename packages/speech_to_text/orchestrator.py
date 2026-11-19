"""
Streaming Speech-to-Text Orchestrator for SDK-9 Co-Pilot.

Integrates:
- Audio frame ingestion (from MockMicrophoneSource or live audio)
- Acoustic preprocessing (16kHz resampling, amplitude normalization)
- Provider interface dispatch with bounded retries and error normalization
- Monotonic segment ordering, duplicate suppression, and interim-final reconciliation
- High-level session lifecycle (start, pause, resume, flush, stop)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Generator, List, Optional

from packages.speech_to_text.accumulator import SegmentAccumulator
from packages.speech_to_text.exceptions import STTError, normalize_stt_exception
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.models import (
    AccumulatedUtterance,
    AccumulatorState,
    TranscriptEvent,
    TranscriptSegment,
)
from packages.speech_to_text.preprocessor import AudioPreprocessor
from packages.speech_to_text.reconciler import TranscriptReconciler
from packages.speech_to_text.retry import BoundedRetryHandler


class OrchestratorState:
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class SpeechToTextOrchestrator:
    """Full-lifecycle orchestrator converting incoming audio frames into reconciled transcript events."""

    def __init__(
        self,
        session_id: str = "stt-orchestrator-session",
        transcriber: Optional[Any] = None,
        preprocessor: Optional[AudioPreprocessor] = None,
        retry_handler: Optional[BoundedRetryHandler] = None,
        on_event: Optional[Callable[[TranscriptEvent], None]] = None,
    ) -> None:
        self.session_id = session_id
        self.transcriber = transcriber or FakeTranscriberService()
        self.preprocessor = preprocessor or AudioPreprocessor()
        self.retry_handler = retry_handler or BoundedRetryHandler()
        self.on_event = on_event

        self.reconciler = TranscriptReconciler(session_id=session_id)
        self.accumulator = SegmentAccumulator(session_id=session_id)

        self._state: str = OrchestratorState.IDLE
        self._buffered_pcm = bytearray()
        self._total_frames_processed: int = 0
        self._total_audio_bytes_ingested: int = 0
        self._events_emitted: List[TranscriptEvent] = []
        self._min_chunk_bytes: int = 3200  # 100ms at 16kHz 16-bit mono = 3200 bytes

    @property
    def state(self) -> str:
        return self._state

    @property
    def total_frames_processed(self) -> int:
        return self._total_frames_processed

    @property
    def total_audio_bytes_ingested(self) -> int:
        return self._total_audio_bytes_ingested

    @property
    def events_emitted(self) -> List[TranscriptEvent]:
        return list(self._events_emitted)

    def start(self) -> None:
        """Start the orchestrator session."""
        self._state = OrchestratorState.RUNNING
        self._buffered_pcm.clear()
        self.reconciler.clear()
        self.accumulator.clear()
        self._events_emitted.clear()

    def pause(self) -> None:
        """Pause listening (e.g. during VAD silence)."""
        if self._state == OrchestratorState.RUNNING:
            self._state = OrchestratorState.PAUSED
            self.accumulator.pause()

    def resume(self) -> None:
        """Resume listening."""
        if self._state == OrchestratorState.PAUSED:
            self._state = OrchestratorState.RUNNING
            self.accumulator.resume()

    def push_audio(
        self,
        audio_payload: bytes | Any,
        sample_rate: int = 16000,
        channels: int = 1,
        timestamp: Optional[float] = None,
        is_speech: bool = True,
    ) -> List[TranscriptEvent]:
        """Ingest raw audio bytes or an AudioFrame, preprocess, and process transcription.

        Args:
            audio_payload: Raw PCM bytes or object with a `.data` bytes attribute (like AudioFrame).
            sample_rate: Source sampling rate (ignored if audio_payload has `.sample_rate`).
            channels: Number of channels (ignored if audio_payload has `.channels`).
            timestamp: Epoch timestamp of the audio.
            is_speech: Flag from VAD indicating speech presence.

        Returns:
            List of new :class:`~packages.speech_to_text.models.TranscriptEvent` objects.
        """
        if self._state == OrchestratorState.PAUSED or not is_speech:
            return []

        if self._state == OrchestratorState.IDLE:
            self.start()

        # Extract payload data if an AudioFrame object was passed
        if hasattr(audio_payload, "data") and isinstance(audio_payload.data, bytes):
            pcm_raw = audio_payload.data
            sr = getattr(audio_payload, "sample_rate", sample_rate)
            ch = getattr(audio_payload, "channels", channels)
            ts = getattr(audio_payload, "timestamp", timestamp or time.time())
        else:
            pcm_raw = bytes(audio_payload)
            sr = sample_rate
            ch = channels
            ts = timestamp or time.time()

        if not pcm_raw:
            return []

        self._total_frames_processed += 1
        self._total_audio_bytes_ingested += len(pcm_raw)

        # 1. Preprocess audio (resample to 16kHz mono, normalize amplitude)
        try:
            clean_pcm = self.preprocessor.process(pcm_raw, source_sample_rate=sr, channels=ch)
        except Exception as exc:
            raise normalize_stt_exception(exc) from exc

        self._buffered_pcm.extend(clean_pcm)
        events: List[TranscriptEvent] = []

        # 2. Check if we have enough accumulated audio for a transcription step
        if len(self._buffered_pcm) >= self._min_chunk_bytes:
            chunk_to_transcribe = bytes(self._buffered_pcm)
            self._buffered_pcm.clear()

            # 3. Transcribe through provider with bounded retries
            try:
                segments = self.retry_handler.execute(
                    self.transcriber.transcribe,
                    chunk_to_transcribe,
                    start_time_offset=ts,
                )
            except Exception as exc:
                self._state = OrchestratorState.ERROR
                raise normalize_stt_exception(exc) from exc

            # 4. Reconcile and accumulate segments
            for seg in segments:
                event = self.reconciler.process_segment(seg)
                if event is not None:
                    self.accumulator.add_segment(seg)
                    self._events_emitted.append(event)
                    events.append(event)
                    if self.on_event:
                        self.on_event(event)

        return events

    def flush(self) -> Optional[TranscriptEvent]:
        """Flush remaining buffered audio and commit pending interim segments as final."""
        events: List[TranscriptEvent] = []

        # Transcribe any residual buffered audio
        if len(self._buffered_pcm) > 0:
            chunk_to_transcribe = bytes(self._buffered_pcm)
            self._buffered_pcm.clear()
            try:
                segments = self.transcriber.transcribe(chunk_to_transcribe)
                for seg in segments:
                    ev = self.reconciler.process_segment(seg)
                    if ev:
                        self.accumulator.add_segment(seg)
                        self._events_emitted.append(ev)
                        events.append(ev)
                        if self.on_event:
                            self.on_event(ev)
            except Exception as exc:
                raise normalize_stt_exception(exc) from exc

        # Promote any active interim to final
        flushed_event = self.reconciler.flush()
        if flushed_event:
            self._events_emitted.append(flushed_event)
            if self.on_event:
                self.on_event(flushed_event)
            return flushed_event

        return None

    def finalize_utterance(self) -> AccumulatedUtterance:
        """Synthesize all reconciled segments into a complete cohesive utterance."""
        self.flush()
        utterance = self.accumulator.finalize_utterance()
        # Emit utterance event
        utt_event = TranscriptEvent(
            event_type="transcript.utterance",
            session_id=self.session_id,
            utterance=utterance,
            timestamp=time.time(),
        )
        self._events_emitted.append(utt_event)
        if self.on_event:
            self.on_event(utt_event)
        return utterance

    def stop(self) -> AccumulatedUtterance:
        """Stop session, finalize utterance, and transition to STOPPED."""
        utterance = self.finalize_utterance()
        self._state = OrchestratorState.STOPPED
        return utterance

    def get_full_transcript(self) -> str:
        """Return the current complete transcript."""
        return self.reconciler.get_full_transcript()
