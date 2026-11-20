"""
Streaming Speech-to-Text Orchestrator for SDK-9 Co-Pilot.

Integrates:
- Audio frame ingestion (from MockMicrophoneSource or live audio)
- Acoustic preprocessing (16kHz resampling, amplitude normalization)
- Provider interface dispatch with bounded retries and error normalization
- Monotonic segment ordering, duplicate suppression, and interim-final reconciliation
- High-level session lifecycle (start, pause, resume, cancel, flush, stop)
- Automatic fallback from primary provider failure (e.g. quota, network) to mock provider
- Session-linked revision and finalization event routing
- Configurable confidence threshold handling
- Tracking and graceful handling of out-of-order chunks and missing frame gaps
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Generator, List, Optional

from packages.speech_to_text.accumulator import SegmentAccumulator
from packages.speech_to_text.exceptions import (
    STTConnectionError,
    STTError,
    STTProviderError,
    STTQuotaExceededError,
    STTRateLimitError,
    STTTimeoutError,
    normalize_stt_exception,
)
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
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class SpeechToTextOrchestrator:
    """Full-lifecycle orchestrator converting incoming audio frames into reconciled transcript events."""

    def __init__(
        self,
        session_id: str = "stt-orchestrator-session",
        correlation_id: Optional[str] = None,
        transcriber: Optional[Any] = None,
        fallback_transcriber: Optional[Any] = None,
        preprocessor: Optional[AudioPreprocessor] = None,
        retry_handler: Optional[BoundedRetryHandler] = None,
        on_event: Optional[Callable[[TranscriptEvent], None]] = None,
        confidence_threshold: float = 0.65,
        low_confidence_action: str = "tag",
        enable_revision_events: bool = False,
        enable_fallback: bool = True,
    ) -> None:
        self.session_id = session_id
        self.correlation_id = correlation_id
        self.transcriber = transcriber or FakeTranscriberService()
        self.fallback_transcriber = fallback_transcriber or (
            FakeTranscriberService() if not isinstance(self.transcriber, FakeTranscriberService) else None
        )
        self.enable_fallback = enable_fallback
        self.preprocessor = preprocessor or AudioPreprocessor()
        self.retry_handler = retry_handler or BoundedRetryHandler()
        self.on_event = on_event

        self.confidence_threshold = confidence_threshold
        self.low_confidence_action = low_confidence_action
        self.enable_revision_events = enable_revision_events

        self.reconciler = TranscriptReconciler(
            session_id=session_id,
            correlation_id=correlation_id,
            confidence_threshold=confidence_threshold,
            low_confidence_action=low_confidence_action,
            emit_revised_events=enable_revision_events,
        )
        self.accumulator = SegmentAccumulator(session_id=session_id)

        self._lock = threading.RLock()
        self._state: str = OrchestratorState.IDLE
        self._buffered_pcm = bytearray()
        self._total_frames_processed: int = 0
        self._total_audio_bytes_ingested: int = 0
        self._events_emitted: List[TranscriptEvent] = []
        self._min_chunk_bytes: int = 3200  # 100ms at 16kHz 16-bit mono = 3200 bytes

        # Out-of-order & sequence gap tracking
        self._last_sequence_num: Optional[int] = None
        self._missing_chunks_count: int = 0
        self._out_of_order_chunks_count: int = 0
        self._fallback_active: bool = False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def total_frames_processed(self) -> int:
        with self._lock:
            return self._total_frames_processed

    @property
    def total_audio_bytes_ingested(self) -> int:
        with self._lock:
            return self._total_audio_bytes_ingested

    @property
    def events_emitted(self) -> List[TranscriptEvent]:
        with self._lock:
            return list(self._events_emitted)

    @property
    def missing_chunks_count(self) -> int:
        with self._lock:
            return self._missing_chunks_count

    @property
    def out_of_order_chunks_count(self) -> int:
        with self._lock:
            return self._out_of_order_chunks_count

    @property
    def is_fallback_active(self) -> bool:
        with self._lock:
            return self._fallback_active

    def start(self) -> None:
        """Start the orchestrator session."""
        with self._lock:
            self._state = OrchestratorState.RUNNING
            self._buffered_pcm.clear()
            self.reconciler.clear()
            self.accumulator.clear()
            self._events_emitted.clear()
            self._last_sequence_num = None
            self._missing_chunks_count = 0
            self._out_of_order_chunks_count = 0
            self._fallback_active = False

    def pause(self) -> None:
        """Pause listening (e.g. during VAD silence)."""
        with self._lock:
            if self._state == OrchestratorState.RUNNING:
                self._state = OrchestratorState.PAUSED
                self.accumulator.pause()

    def resume(self) -> None:
        """Resume listening."""
        with self._lock:
            if self._state == OrchestratorState.PAUSED:
                self._state = OrchestratorState.RUNNING
                self.accumulator.resume()

    def cancel(self, reason: str = "Client requested cancellation") -> TranscriptEvent:
        """Stop in-flight transcription cleanly and release active buffers.

        - Clears buffered PCM audio.
        - Discards pending interim segments.
        - Emits a normalized transcript.cancelled event with session_id.
        - Sets state to CANCELLED without raising unhandled exceptions.
        """
        with self._lock:
            self._state = OrchestratorState.CANCELLED
            self._buffered_pcm.clear()
            self.reconciler.clear_interim()

            cancel_event = TranscriptEvent(
                event_type="transcript.cancelled",
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                details={"reason": reason},
                timestamp=time.time(),
            )
            self._events_emitted.append(cancel_event)
            if self.on_event:
                try:
                    self.on_event(cancel_event)
                except Exception:
                    pass
            return cancel_event

    def push_audio(
        self,
        audio_payload: bytes | Any,
        sample_rate: int = 16000,
        channels: int = 1,
        timestamp: Optional[float] = None,
        is_speech: bool = True,
        sequence_number: Optional[int] = None,
    ) -> List[TranscriptEvent]:
        """Ingest raw audio bytes or an AudioFrame, preprocess, and process transcription.

        Args:
            audio_payload: Raw PCM bytes or object with a `.data` bytes attribute (like AudioFrame).
            sample_rate: Source sampling rate (ignored if audio_payload has `.sample_rate`).
            channels: Number of channels (ignored if audio_payload has `.channels`).
            timestamp: Epoch timestamp of the audio.
            is_speech: Flag from VAD indicating speech presence.
            sequence_number: Optional monotonic chunk sequence number.

        Returns:
            List of new :class:`~packages.speech_to_text.models.TranscriptEvent` objects.
        """
        with self._lock:
            if self._state in (OrchestratorState.PAUSED, OrchestratorState.CANCELLED) or not is_speech:
                return []

            if self._state == OrchestratorState.IDLE:
                self.start()

            # Sequence and gap tracking
            seq = sequence_number
            if seq is None and hasattr(audio_payload, "sequence_number"):
                seq = getattr(audio_payload, "sequence_number")
            elif seq is None and hasattr(audio_payload, "frame_index"):
                seq = getattr(audio_payload, "frame_index")

            if seq is not None:
                if self._last_sequence_num is not None:
                    if seq <= self._last_sequence_num:
                        self._out_of_order_chunks_count += 1
                    elif seq > self._last_sequence_num + 1:
                        self._missing_chunks_count += (seq - self._last_sequence_num - 1)
                self._last_sequence_num = seq

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

                # 3. Transcribe through provider with bounded retries & fallback protection
                segments = self._transcribe_with_fallback(chunk_to_transcribe, ts, events)

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

    def _transcribe_with_fallback(
        self,
        chunk_to_transcribe: bytes,
        timestamp: float,
        events_out: List[TranscriptEvent],
    ) -> List[TranscriptSegment]:
        """Execute transcription with primary provider; fall back to mock provider on network/quota error."""
        active_transcriber = self.fallback_transcriber if self._fallback_active else self.transcriber

        try:
            return self.retry_handler.execute(
                active_transcriber.transcribe,
                chunk_to_transcribe,
                start_time_offset=timestamp,
            )
        except Exception as exc:
            normalized = normalize_stt_exception(exc)

            # Week 3 Acceptance Criteria:
            # "quota or network failures fall back to the mock provider with a normalized error"
            is_fallback_eligible = isinstance(
                normalized,
                (STTQuotaExceededError, STTRateLimitError, STTConnectionError, STTTimeoutError),
            )

            if self.enable_fallback and self.fallback_transcriber is not None and is_fallback_eligible and not self._fallback_active:
                self._fallback_active = True
                fallback_name = getattr(self.fallback_transcriber, "__class__", type(self.fallback_transcriber)).__name__

                fallback_event = TranscriptEvent(
                    event_type="transcript.fallback",
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    is_fallback=True,
                    details={
                        "reason": normalized.message,
                        "error_code": normalized.code,
                        "fallback_provider": fallback_name,
                    },
                    timestamp=time.time(),
                )
                self._events_emitted.append(fallback_event)
                events_out.append(fallback_event)
                if self.on_event:
                    try:
                        self.on_event(fallback_event)
                    except Exception:
                        pass

                # Attempt transcription via fallback provider
                try:
                    return self.fallback_transcriber.transcribe(chunk_to_transcribe)
                except Exception as fb_exc:
                    self._state = OrchestratorState.ERROR
                    raise normalize_stt_exception(fb_exc) from fb_exc

            self._state = OrchestratorState.ERROR
            raise normalized from exc

    def flush(self) -> Optional[TranscriptEvent]:
        """Flush remaining buffered audio and commit pending interim segments as final."""
        with self._lock:
            if self._state == OrchestratorState.CANCELLED:
                return None

            events: List[TranscriptEvent] = []

            # Transcribe any residual buffered audio
            if len(self._buffered_pcm) > 0:
                chunk_to_transcribe = bytes(self._buffered_pcm)
                self._buffered_pcm.clear()
                try:
                    segments = self._transcribe_with_fallback(chunk_to_transcribe, time.time(), events)
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
        with self._lock:
            self.flush()
            utterance = self.accumulator.finalize_utterance()
            # Emit utterance event
            utt_event = TranscriptEvent(
                event_type="transcript.utterance",
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                utterance=utterance,
                timestamp=time.time(),
            )
            self._events_emitted.append(utt_event)
            if self.on_event:
                self.on_event(utt_event)
            return utterance

    def stop(self) -> AccumulatedUtterance:
        """Stop session, finalize utterance, and transition to STOPPED."""
        with self._lock:
            utterance = self.finalize_utterance()
            self._state = OrchestratorState.STOPPED
            return utterance

    def get_full_transcript(self) -> str:
        """Return the current complete transcript."""
        with self._lock:
            return self.reconciler.get_full_transcript()

