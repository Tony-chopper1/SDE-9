"""
Audio event dispatching, session pipeline coordination, and event envelope generation.
Owner: Satwik A (features/Satwik-week3) - Week 3 (Days 15-16)

Provides:
- AudioEventType: Standardized dot-notated event names conforming to docs/integration-contracts.md.
- AudioEventDispatcher: Thread-safe observer/subscriber registry for EventEnvelope delivery.
- AudioSessionPipeline: Unified pipeline coordinating incoming frames, VAD classification,
  and ordered event emission (speech_start, audio.chunk, speech_end) with session_id and correlation_id.
"""
from __future__ import annotations

from enum import Enum
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from packages.audio.models import (
    AudioFrame,
    EventEnvelope,
    VADEvent,
    VADResult,
    VADState,
)
from packages.audio.vad import BaseVAD, EnergyVAD


class AudioEventType(str, Enum):
    """Standardized event types for Audio & VAD module conforming to SDK-9 integration contracts."""
    SPEECH_START = "audio.vad.speech_start"
    SPEECH_END = "audio.vad.speech_end"
    AUDIO_CHUNK = "audio.chunk"
    STREAM_START = "audio.stream.start"
    STREAM_STOP = "audio.stream.stop"
    DEVICE_LOST = "audio.device.lost"
    DEVICE_RECOVERED = "audio.device.recovered"
    STREAM_CANCELLED = "audio.stream.cancelled"


class AudioEventDispatcher:
    """Thread-safe event dispatcher and subscriber registry for EventEnvelope instances."""

    def __init__(self) -> None:
        self._subscribers: List[Tuple[Callable[[EventEnvelope], None], Optional[str]]] = []
        self._history: List[EventEnvelope] = []
        self._lock = threading.RLock()

    def subscribe(
        self,
        listener: Callable[[EventEnvelope], None],
        event_type: Optional[str] = None,
    ) -> None:
        """Register a callback for emitted events.

        Args:
            listener: Callable accepting an EventEnvelope.
            event_type: Optional event_type filter. If None, receives all events.
        """
        with self._lock:
            self._subscribers.append((listener, event_type))

    def unsubscribe(self, listener: Callable[[EventEnvelope], None]) -> bool:
        """Unregister a previously registered callback.

        Returns:
            True if listener was found and removed, False otherwise.
        """
        with self._lock:
            original_len = len(self._subscribers)
            self._subscribers = [s for s in self._subscribers if s[0] != listener]
            return len(self._subscribers) < original_len

    def dispatch(self, event: EventEnvelope) -> None:
        """Deliver an EventEnvelope to matching subscribers and record in history."""
        with self._lock:
            self._history.append(event)
            for listener, filter_type in self._subscribers:
                if filter_type is None or filter_type == event.event_type:
                    try:
                        listener(event)
                    except Exception:
                        # Listener faults must never crash the pipeline
                        pass

    @property
    def history(self) -> List[EventEnvelope]:
        """Chronological history of all dispatched events."""
        with self._lock:
            return list(self._history)

    def get_events(self, event_type: Optional[str] = None) -> List[EventEnvelope]:
        """Filter dispatched history by event_type."""
        with self._lock:
            if event_type is None:
                return list(self._history)
            return [e for e in self._history if e.event_type == event_type]

    def clear(self) -> None:
        """Clear recorded event history."""
        with self._lock:
            self._history.clear()


class AudioSessionPipeline:
    """Unified session pipeline coordinating audio frame ingestion, VAD, and event emission.

    Guarantees:
    - Automatically detects speech start and speech end transitions.
    - Emits speech_start BEFORE the first speech chunk.
    - Emits speech_end immediately when speech transitions back to silence.
    - Emits normalized audio.chunk envelopes for all frames.
    - Strict monotonic chronological ordering for all events.
    - Every event carries consistent session_id and correlation_id.
    - Clean flush() guarantees active speech segments are bounded on stream finish.
    """

    def __init__(
        self,
        session_id: str,
        correlation_id: Optional[str] = None,
        vad: Optional[BaseVAD] = None,
        dispatcher: Optional[AudioEventDispatcher] = None,
        on_event: Optional[Callable[[EventEnvelope], None]] = None,
        emit_chunk_events: bool = True,
        include_raw_bytes_in_chunk: bool = False,
    ) -> None:
        """Initialize the audio session pipeline.

        Args:
            session_id: Session identifier.
            correlation_id: Tracing correlation ID (auto-generated if omitted).
            vad: BaseVAD instance (defaults to EnergyVAD(threshold_db=-42.0)).
            dispatcher: AudioEventDispatcher for broadcasting (creates new one if omitted).
            on_event: Optional single callback invoked for every emitted event.
            emit_chunk_events: Whether to emit 'audio.chunk' event envelopes for every frame.
            include_raw_bytes_in_chunk: Whether to include base64 PCM bytes in audio.chunk payloads.
        """
        if not session_id:
            raise ValueError("session_id must not be empty")

        self.session_id = session_id
        self.correlation_id = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
        self.vad = vad or EnergyVAD()
        self.dispatcher = dispatcher or AudioEventDispatcher()
        self.emit_chunk_events = emit_chunk_events
        self.include_raw_bytes_in_chunk = include_raw_bytes_in_chunk

        if on_event is not None:
            self.dispatcher.subscribe(on_event)

        self._lock = threading.RLock()
        self._in_speech = False
        self._is_cancelled = False
        self._is_device_lost = False
        self._speech_start_frame: Optional[int] = None
        self._speech_start_ms: Optional[float] = None
        self._speech_start_epoch: Optional[float] = None
        self._speech_frames_count = 0
        self._total_frames_processed = 0
        self._speech_segments_count = 0
        self._emitted_events: List[EventEnvelope] = []

    @property
    def in_speech(self) -> bool:
        """True if the pipeline is currently tracking an active speech segment."""
        with self._lock:
            return self._in_speech

    @property
    def is_cancelled(self) -> bool:
        """True if session was cancelled."""
        with self._lock:
            return self._is_cancelled

    @property
    def is_device_lost(self) -> bool:
        """True if currently in a device-lost state."""
        with self._lock:
            return self._is_device_lost

    @property
    def total_frames_processed(self) -> int:
        with self._lock:
            return self._total_frames_processed

    @property
    def speech_segments_count(self) -> int:
        with self._lock:
            return self._speech_segments_count

    @property
    def events(self) -> List[EventEnvelope]:
        """All EventEnvelope instances generated by this pipeline."""
        with self._lock:
            return list(self._emitted_events)

    def _emit(self, event: EventEnvelope) -> None:
        """Record and broadcast an event."""
        self._emitted_events.append(event)
        self.dispatcher.dispatch(event)

    def process_frame(self, frame: AudioFrame) -> List[EventEnvelope]:
        """Ingest an AudioFrame, evaluate VAD, and emit ordered events.

        Ordering Guarantee:
        1. If transitioning SILENCE -> SPEECH:
           Emits 'audio.vad.speech_start' FIRST, then 'audio.chunk'.
        2. If transitioning SPEECH -> SILENCE:
           Emits 'audio.vad.speech_end' FIRST, then 'audio.chunk'.
        3. Otherwise:
           Emits 'audio.chunk'.

        Args:
            frame: Input AudioFrame instance.

        Returns:
            List of EventEnvelope instances emitted during this frame's processing.
        """
        with self._lock:
            if self._is_cancelled or self._is_device_lost:
                return []
            self._total_frames_processed += 1
            step_events: List[EventEnvelope] = []

            # 1. Evaluate VAD
            vad_res: VADResult = self.vad.process_frame(frame)
            frame.is_speech = vad_res.is_speech

            # 2. State transition detection
            is_speech_now = vad_res.is_speech
            prior_speech = self._in_speech

            # Case A: Transition SILENCE -> SPEECH (Speech Start)
            if is_speech_now and not prior_speech:
                self._in_speech = True
                self._speech_start_frame = frame.frame_index
                self._speech_start_ms = frame.timestamp_ms
                self._speech_start_epoch = frame.timestamp
                self._speech_frames_count = 1
                self._speech_segments_count += 1

                start_envelope = EventEnvelope.create(
                    event_type=AudioEventType.SPEECH_START.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": VADState.SPEECH_START.value,
                        "frame_id": frame.frame_id,
                        "frame_index": frame.frame_index,
                        "sequence_number": frame.sequence_number,
                        "timestamp_ms": frame.timestamp_ms,
                        "timestamp_epoch": frame.timestamp,
                        "energy_db": vad_res.energy_db,
                        "confidence": vad_res.confidence,
                        "segment_index": self._speech_segments_count,
                    },
                )
                self._emit(start_envelope)
                step_events.append(start_envelope)

            # Case B: Speech ongoing
            elif is_speech_now and prior_speech:
                self._speech_frames_count += 1

            # Case C: Transition SPEECH -> SILENCE (Speech End)
            elif not is_speech_now and prior_speech:
                self._in_speech = False
                dur_ms = max(
                    0.0,
                    frame.timestamp_ms - (self._speech_start_ms if self._speech_start_ms is not None else 0.0),
                )
                end_envelope = EventEnvelope.create(
                    event_type=AudioEventType.SPEECH_END.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": VADState.SPEECH_END.value,
                        "frame_id": frame.frame_id,
                        "frame_index": frame.frame_index,
                        "sequence_number": frame.sequence_number,
                        "timestamp_ms": frame.timestamp_ms,
                        "timestamp_epoch": frame.timestamp,
                        "energy_db": vad_res.energy_db,
                        "confidence": vad_res.confidence,
                        "speech_duration_ms": round(dur_ms, 2),
                        "speech_frames_count": self._speech_frames_count,
                        "segment_index": self._speech_segments_count,
                    },
                )
                self._emit(end_envelope)
                step_events.append(end_envelope)

            # 3. Emit normalized audio chunk event
            if self.emit_chunk_events:
                chunk_payload: Dict[str, Any] = {
                    "frame_id": frame.frame_id,
                    "chunk_id": frame.frame_id,
                    "frame_index": frame.frame_index,
                    "chunk_index": frame.frame_index,
                    "sequence_number": frame.sequence_number,
                    "timestamp": frame.timestamp,
                    "timestamp_ms": round(frame.timestamp_ms, 2),
                    "timestamp_utc": frame.timestamp_utc,
                    "sample_rate": frame.sample_rate,
                    "channels": frame.channels,
                    "format": frame.format,
                    "frame_duration_ms": frame.frame_duration_ms,
                    "byte_length": len(frame.data),
                    "is_speech": frame.is_speech,
                    "energy_db": vad_res.energy_db,
                    "rms": round(frame.calculate_rms(), 2),
                    "dbfs": round(frame.calculate_dbfs(), 2),
                }
                import base64
                chunk_payload["audio_data_base64"] = base64.b64encode(frame.data).decode("ascii")

                chunk_envelope = EventEnvelope.create(
                    event_type=AudioEventType.AUDIO_CHUNK.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload=chunk_payload,
                )
                self._emit(chunk_envelope)
                step_events.append(chunk_envelope)

            return step_events

    def flush(self) -> List[EventEnvelope]:
        """Flush the pipeline on stream completion.

        If a speech segment is still active, cleanly emits a trailing 'audio.vad.speech_end'
        event so downstream consumers receive a bounded utterance.
        """
        with self._lock:
            flush_events: List[EventEnvelope] = []
            if self._in_speech:
                self._in_speech = False
                end_envelope = EventEnvelope.create(
                    event_type=AudioEventType.SPEECH_END.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": VADState.SPEECH_END.value,
                        "frame_id": "eos",
                        "frame_index": self._total_frames_processed,
                        "sequence_number": self._total_frames_processed,
                        "timestamp_ms": None,
                        "timestamp_epoch": None,
                        "energy_db": None,
                        "confidence": 1.0,
                        "speech_frames_count": self._speech_frames_count,
                        "segment_index": self._speech_segments_count,
                        "reason": "end_of_stream_flush",
                    },
                )
                self._emit(end_envelope)
                flush_events.append(end_envelope)
            return flush_events

    def handle_device_loss(
        self,
        device_id: Optional[str] = None,
        reason: str = "device_disconnected",
    ) -> Optional[EventEnvelope]:
        """Notify pipeline that active audio capture device was lost or disconnected.

        Guarantees:
        - If active speech was in progress, cleanly emits a bounded 'speech_end' interruption event.
        - Emits standardized 'audio.device.lost' EventEnvelope.
        - Suppresses duplicate loss events if already in device_lost state.
        """
        with self._lock:
            if self._is_device_lost or self._is_cancelled:
                return None
            self._is_device_lost = True

            # If currently in speech, terminate the segment cleanly
            if self._in_speech:
                self._in_speech = False
                speech_end_env = EventEnvelope.create(
                    event_type=AudioEventType.SPEECH_END.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": VADState.SPEECH_END.value,
                        "frame_id": "device_lost",
                        "frame_index": self._total_frames_processed,
                        "sequence_number": self._total_frames_processed,
                        "timestamp_ms": None,
                        "timestamp_epoch": None,
                        "energy_db": None,
                        "confidence": 1.0,
                        "speech_frames_count": self._speech_frames_count,
                        "segment_index": self._speech_segments_count,
                        "reason": "device_loss_interruption",
                    },
                )
                self._emit(speech_end_env)

            loss_env = EventEnvelope.create(
                event_type=AudioEventType.DEVICE_LOST.value,
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                payload={
                    "state": "DEVICE_LOST",
                    "device_id": device_id,
                    "reason": reason,
                    "total_frames_before_loss": self._total_frames_processed,
                },
            )
            self._emit(loss_env)
            return loss_env

    def handle_device_recovery(
        self,
        device_id: str,
        is_fallback: bool = False,
    ) -> Optional[EventEnvelope]:
        """Notify pipeline that audio device connection has been restored or switched to fallback.

        Guarantees:
        - Emits standardized 'audio.device.recovered' EventEnvelope.
        - Preserves existing session_id and correlation_id.
        - Avoids duplicate recovery events if not in device_lost state.
        """
        with self._lock:
            if not self._is_device_lost or self._is_cancelled:
                return None
            self._is_device_lost = False

            rec_env = EventEnvelope.create(
                event_type=AudioEventType.DEVICE_RECOVERED.value,
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                payload={
                    "state": "DEVICE_RECOVERED",
                    "device_id": device_id,
                    "is_fallback": is_fallback,
                    "session_id": self.session_id,
                    "correlation_id": self.correlation_id,
                },
            )
            self._emit(rec_env)
            return rec_env

    def cancel(self, reason: str = "user_cancelled") -> List[EventEnvelope]:
        """Atomically cancel the session pipeline.

        Guarantees:
        - Stops further frame ingestion (subsequent process_frame calls return []).
        - Closes active speech burst with speech_end if currently speaking.
        - Emits standardized 'audio.stream.cancelled' EventEnvelope.
        - Safe and idempotent on repeated calls.
        """
        with self._lock:
            if self._is_cancelled:
                return []
            self._is_cancelled = True
            cancel_events: List[EventEnvelope] = []

            # Cleanly conclude ongoing speech burst if active
            if self._in_speech:
                self._in_speech = False
                end_env = EventEnvelope.create(
                    event_type=AudioEventType.SPEECH_END.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": VADState.SPEECH_END.value,
                        "frame_id": "cancelled",
                        "frame_index": self._total_frames_processed,
                        "sequence_number": self._total_frames_processed,
                        "timestamp_ms": None,
                        "timestamp_epoch": None,
                        "energy_db": None,
                        "confidence": 1.0,
                        "speech_frames_count": self._speech_frames_count,
                        "segment_index": self._speech_segments_count,
                        "reason": "cancellation",
                    },
                )
                self._emit(end_env)
                cancel_events.append(end_env)

            cancel_env = EventEnvelope.create(
                event_type=AudioEventType.STREAM_CANCELLED.value,
                session_id=self.session_id,
                correlation_id=self.correlation_id,
                payload={
                    "state": "CANCELLED",
                    "reason": reason,
                    "total_frames_processed": self._total_frames_processed,
                },
            )
            self._emit(cancel_env)
            cancel_events.append(cancel_env)
            return cancel_events

    def reset(self) -> None:
        """Reset pipeline state and VAD temporal smoothing buffers."""
        with self._lock:
            self.vad.reset()
            self._in_speech = False
            self._speech_start_frame = None
            self._speech_start_ms = None
            self._speech_start_epoch = None
            self._speech_frames_count = 0
            self._total_frames_processed = 0
            self._speech_segments_count = 0
            self._emitted_events.clear()


__all__ = [
    "AudioEventType",
    "AudioEventDispatcher",
    "AudioSessionPipeline",
]
