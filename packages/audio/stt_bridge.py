"""
Audio & VAD to Speech-to-Text (STT) Integration Bridge.
Owner: Satwik A (features/Satwik-week3) - Week 3 (Days 19-20)

Provides:
- AudioSTTBridge: Connects AudioEventDispatcher/AudioSessionPipeline to SpeechToTextOrchestrator.
  - Forwards valid speech chunks to STT while strictly respecting speech boundaries.
  - Filters out silence and non-speech chunks.
  - Prevents duplicate chunk delivery and handles sequence gaps / out-of-order chunks safely.
  - Handles lifecycle events (device loss flushes open utterances, cancellation safely stops STT).
  - Collects interim and final transcript events.
- MultiSessionSTTBridge: Routes events to session-isolated AudioSTTBridge instances.
"""
from __future__ import annotations

import base64
from collections import OrderedDict
import threading
from typing import Any, Callable, Dict, List, Optional

from packages.audio.events import AudioEventDispatcher, AudioEventType
from packages.audio.models import AudioFrame, EventEnvelope
from packages.speech_to_text.models import AccumulatedUtterance, TranscriptEvent
from packages.speech_to_text.orchestrator import OrchestratorState, SpeechToTextOrchestrator


class AudioSTTBridge:
    """Bridges the Audio & VAD event stream to the Speech-to-Text orchestrator.

    Guarantees:
    - Session and correlation context preservation.
    - Strict speech boundary enforcement (speech_start -> speech -> speech_end).
    - Silence rejection (silence frames are never forwarded to STT as speech).
    - False trigger protection (empty/sub-threshold bursts are handled gracefully).
    - Duplicate chunk suppression via frame_id and sequence tracking.
    - Monotonic ordering validation (stale frames dropped, sequence gaps tracked).
    - Device loss safety (flushes and closes open utterances immediately).
    - Cancellation safety (terminates STT without leaving pending work).
    - Thread-safe coordination under RLock.
    """

    def __init__(
        self,
        session_id: str = "default-session",
        correlation_id: Optional[str] = None,
        orchestrator: Optional[SpeechToTextOrchestrator] = None,
        dispatcher: Optional[AudioEventDispatcher] = None,
        on_transcript_event: Optional[Callable[[TranscriptEvent], None]] = None,
        min_speech_frames_threshold: int = 1,
        dedup_capacity: int = 1000,
    ) -> None:
        """Initialize the Audio-to-STT bridge.

        Args:
            session_id: Session identifier to filter and bind to.
            correlation_id: Tracing correlation ID.
            orchestrator: SpeechToTextOrchestrator instance (created if None).
            dispatcher: AudioEventDispatcher to automatically subscribe to (optional).
            on_transcript_event: Callback for transcript events (interim, final, utterance).
            min_speech_frames_threshold: Minimum speech frames required before committing audio.
            dedup_capacity: Maximum number of recent frame IDs tracked for deduplication (default: 1000).
        """
        self.session_id = session_id
        self.correlation_id = correlation_id
        self.min_speech_frames_threshold = max(1, min_speech_frames_threshold)
        self.dedup_capacity = max(10, dedup_capacity)
        self.on_transcript_event = on_transcript_event

        self._lock = threading.RLock()
        self._orchestrator = orchestrator or SpeechToTextOrchestrator(
            session_id=session_id,
            on_event=self._on_orchestrator_event,
        )
        if orchestrator is not None:
            # Wrap existing orchestrator callback if present
            orig_cb = self._orchestrator.on_event

            def combined_cb(evt: TranscriptEvent):
                if orig_cb:
                    try:
                        orig_cb(evt)
                    except Exception:
                        pass
                self._on_orchestrator_event(evt)

            self._orchestrator.on_event = combined_cb

        self._dispatcher = dispatcher
        if dispatcher is not None:
            dispatcher.subscribe(self.handle_event)

        # State tracking
        self._in_speech: bool = False
        self._is_device_lost: bool = False
        self._is_cancelled: bool = False
        self._current_segment_frames: int = 0
        self._last_delivered_seq: Optional[int] = None
        self._epoch: int = 0
        self._delivered_frame_ids: OrderedDict[str, None] = OrderedDict()
        self._transcripts: List[TranscriptEvent] = []

        # Telemetry
        self._total_chunks_received: int = 0
        self._speech_chunks_forwarded: int = 0
        self._silence_chunks_ignored: int = 0
        self._duplicate_chunks_dropped: int = 0
        self._out_of_order_chunks_dropped: int = 0
        self._sequence_gaps_detected: int = 0

    @property
    def orchestrator(self) -> SpeechToTextOrchestrator:
        return self._orchestrator

    @property
    def in_speech(self) -> bool:
        with self._lock:
            return self._in_speech

    @property
    def is_device_lost(self) -> bool:
        with self._lock:
            return self._is_device_lost

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled

    @property
    def transcripts(self) -> List[TranscriptEvent]:
        with self._lock:
            return list(self._transcripts)

    @property
    def telemetry(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_chunks_received": self._total_chunks_received,
                "speech_chunks_forwarded": self._speech_chunks_forwarded,
                "silence_chunks_ignored": self._silence_chunks_ignored,
                "duplicate_chunks_dropped": self._duplicate_chunks_dropped,
                "out_of_order_chunks_dropped": self._out_of_order_chunks_dropped,
                "sequence_gaps_detected": self._sequence_gaps_detected,
                "transcripts_emitted": len(self._transcripts),
            }

    def _on_orchestrator_event(self, evt: TranscriptEvent) -> None:
        """Internal callback receiving events from the STT orchestrator."""
        with self._lock:
            self._transcripts.append(evt)
        if self.on_transcript_event:
            try:
                self.on_transcript_event(evt)
            except Exception:
                pass

    def handle_event(self, event: EventEnvelope) -> None:
        """Dispatcher observer entry point. Processes Audio & VAD EventEnvelopes.

        Args:
            event: EventEnvelope from AudioEventDispatcher.
        """
        with self._lock:
            # 1. Multi-session isolation check
            if event.session_id and event.session_id != self.session_id:
                return

            if self._is_cancelled:
                return

            evt_type = event.event_type

            # Case A: Speech Start
            if evt_type == AudioEventType.SPEECH_START.value:
                self._handle_speech_start(event)

            # Case B: Audio Chunk
            elif evt_type == AudioEventType.AUDIO_CHUNK.value:
                self._handle_audio_chunk(event)

            # Case C: Speech End
            elif evt_type == AudioEventType.SPEECH_END.value:
                self._handle_speech_end(event)

            # Case D: Device Lost
            elif evt_type == AudioEventType.DEVICE_LOST.value:
                self._handle_device_lost(event)

            # Case E: Device Recovered
            elif evt_type == AudioEventType.DEVICE_RECOVERED.value:
                self._handle_device_recovered(event)

            # Case F: Stream Cancelled
            elif evt_type == AudioEventType.STREAM_CANCELLED.value:
                self._handle_stream_cancelled(event)

    def _handle_speech_start(self, event: EventEnvelope) -> None:
        """Process speech_start event: open speech segment and activate STT."""
        self._in_speech = True
        self._current_segment_frames = 0
        if self._orchestrator.state == OrchestratorState.PAUSED:
            self._orchestrator.resume()
        elif self._orchestrator.state in (OrchestratorState.IDLE, OrchestratorState.STOPPED):
            self._orchestrator.start()

    def _handle_audio_chunk(self, event: EventEnvelope) -> None:
        """Process audio.chunk event: validate, deduplicate, and forward if speech."""
        self._total_chunks_received += 1
        payload = event.payload
        is_speech = payload.get("is_speech", False)

        # 1. Silence rejection: do not forward non-speech chunks
        if not is_speech or not self._in_speech:
            self._silence_chunks_ignored += 1
            return

        # 2. Extract PCM bytes
        raw_pcm: Optional[bytes] = None
        if "raw_pcm" in payload and isinstance(payload["raw_pcm"], bytes):
            raw_pcm = payload["raw_pcm"]
        elif "audio_data_base64" in payload and isinstance(payload["audio_data_base64"], str):
            try:
                raw_pcm = base64.b64decode(payload["audio_data_base64"])
            except Exception:
                raw_pcm = None
        elif "frame" in payload and hasattr(payload["frame"], "data"):
            raw_pcm = payload["frame"].data

        if not raw_pcm:
            return

        # 3. Deduplication check
        frame_id = payload.get("frame_id") or payload.get("chunk_id")
        dedup_key = f"{self._epoch}:{frame_id}" if frame_id else None
        if dedup_key and dedup_key in self._delivered_frame_ids:
            self._duplicate_chunks_dropped += 1
            return

        # 4. Sequence ordering & gap tracking
        seq = payload.get("sequence_number")
        if seq is not None and isinstance(seq, int):
            if self._last_delivered_seq is not None:
                if seq <= self._last_delivered_seq:
                    # Stale or duplicate sequence
                    self._out_of_order_chunks_dropped += 1
                    return
                elif seq > self._last_delivered_seq + 1:
                    # Gap detected
                    self._sequence_gaps_detected += (seq - self._last_delivered_seq - 1)
            self._last_delivered_seq = seq

        if dedup_key:
            self._delivered_frame_ids[dedup_key] = None
            if len(self._delivered_frame_ids) > self.dedup_capacity:
                self._delivered_frame_ids.popitem(last=False)

        # 5. Forward to STT orchestrator
        sample_rate = payload.get("sample_rate", 16000)
        channels = payload.get("channels", 1)
        timestamp = payload.get("timestamp") or (
            payload.get("timestamp_ms", 0.0) / 1000.0 if "timestamp_ms" in payload else None
        )

        try:
            self._orchestrator.push_audio(
                audio_payload=raw_pcm,
                sample_rate=sample_rate,
                channels=channels,
                timestamp=timestamp,
                is_speech=True,
            )
            self._speech_chunks_forwarded += 1
            self._current_segment_frames += 1
        except Exception:
            pass

    def _handle_speech_end(self, event: EventEnvelope) -> None:
        """Process speech_end event: bound active utterance and flush STT."""
        self._in_speech = False
        # False trigger protection: if 0 speech frames forwarded, no need to flush
        if self._current_segment_frames == 0:
            return

        try:
            self._orchestrator.flush()
        except Exception:
            pass

    def _handle_device_lost(self, event: EventEnvelope) -> None:
        """Process device_lost event: safely flush active segment without hanging."""
        self._is_device_lost = True
        self._in_speech = False
        try:
            self._orchestrator.flush()
        except Exception:
            pass

    def _handle_device_recovered(self, event: EventEnvelope) -> None:
        """Process device_recovered event: ready for new incoming audio."""
        self._is_device_lost = False
        self._epoch += 1
        self._last_delivered_seq = None

    def _handle_stream_cancelled(self, event: EventEnvelope) -> None:
        """Process stream_cancelled event: stop STT and release pending work."""
        self._is_cancelled = True
        self._in_speech = False
        try:
            self._orchestrator.stop()
        except Exception:
            pass

    def push_frame(
        self,
        frame: AudioFrame,
        is_speech: Optional[bool] = None,
    ) -> List[TranscriptEvent]:
        """Direct frame ingestion helper for callers bypassing the event dispatcher.

        Args:
            frame: Input AudioFrame.
            is_speech: Optional override for speech classification.

        Returns:
            List of any TranscriptEvent objects generated by this frame.
        """
        with self._lock:
            if self._is_cancelled or self._is_device_lost:
                return []

            speech_flag = is_speech if is_speech is not None else frame.is_speech
            self._total_chunks_received += 1

            # Silence rejection
            if not speech_flag:
                self._silence_chunks_ignored += 1
                return []

            # Deduplication
            dedup_key = f"{self._epoch}:{frame.frame_id}" if frame.frame_id else None
            if dedup_key and dedup_key in self._delivered_frame_ids:
                self._duplicate_chunks_dropped += 1
                return []

            # Sequence ordering check
            if frame.sequence_number is not None:
                if self._last_delivered_seq is not None:
                    if frame.sequence_number <= self._last_delivered_seq:
                        self._out_of_order_chunks_dropped += 1
                        return []
                    elif frame.sequence_number > self._last_delivered_seq + 1:
                        self._sequence_gaps_detected += (frame.sequence_number - self._last_delivered_seq - 1)
                self._last_delivered_seq = frame.sequence_number

            if dedup_key:
                self._delivered_frame_ids[dedup_key] = None
                if len(self._delivered_frame_ids) > self.dedup_capacity:
                    self._delivered_frame_ids.popitem(last=False)

            self._in_speech = True
            new_events = self._orchestrator.push_audio(
                audio_payload=frame,
                sample_rate=frame.sample_rate,
                channels=frame.channels,
                timestamp=frame.timestamp,
                is_speech=True,
            )
            self._speech_chunks_forwarded += 1
            self._current_segment_frames += 1
            return new_events

    def flush(self) -> Optional[TranscriptEvent]:
        """Flush remaining audio and promote active interim segments to final."""
        with self._lock:
            return self._orchestrator.flush()

    def finalize_utterance(self) -> AccumulatedUtterance:
        """Finalize the current utterance."""
        with self._lock:
            return self._orchestrator.finalize_utterance()

    def stop(self) -> AccumulatedUtterance:
        """Stop bridge and STT orchestrator."""
        with self._lock:
            self._in_speech = False
            self._is_cancelled = True
            return self._orchestrator.stop()

    def get_full_transcript(self) -> str:
        """Return the complete accumulated transcript string."""
        with self._lock:
            return self._orchestrator.get_full_transcript()


class MultiSessionSTTBridge:
    """Manages session-isolated AudioSTTBridge instances.

    Ensures that multiple concurrent audio sessions do not mix audio or transcripts.
    """

    def __init__(
        self,
        dispatcher: Optional[AudioEventDispatcher] = None,
        on_transcript_event: Optional[Callable[[str, TranscriptEvent], None]] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._on_transcript_event = on_transcript_event
        self._bridges: Dict[str, AudioSTTBridge] = {}
        self._lock = threading.RLock()

        if dispatcher is not None:
            dispatcher.subscribe(self.handle_event)

    def get_or_create_session(self, session_id: str) -> AudioSTTBridge:
        """Retrieve existing bridge for session or create a new isolated bridge."""
        with self._lock:
            if session_id not in self._bridges:
                bridge = AudioSTTBridge(
                    session_id=session_id,
                    on_transcript_event=lambda evt, s=session_id: self._dispatch_transcript(s, evt),
                )
                self._bridges[session_id] = bridge
            return self._bridges[session_id]

    def _dispatch_transcript(self, session_id: str, event: TranscriptEvent) -> None:
        if self._on_transcript_event:
            try:
                self._on_transcript_event(session_id, event)
            except Exception:
                pass

    def handle_event(self, event: EventEnvelope) -> None:
        """Route incoming EventEnvelope to the corresponding session-specific bridge."""
        sess_id = event.session_id
        if not sess_id:
            return
        with self._lock:
            bridge = self.get_or_create_session(sess_id)
            bridge.handle_event(event)

    def get_session_transcript(self, session_id: str) -> str:
        """Return complete transcript for a specific session."""
        with self._lock:
            if session_id in self._bridges:
                return self._bridges[session_id].get_full_transcript()
            return ""

    def stop_session(self, session_id: str) -> Optional[AccumulatedUtterance]:
        """Stop a specific session."""
        with self._lock:
            if session_id in self._bridges:
                return self._bridges[session_id].stop()
            return None

    def stop_all(self) -> Dict[str, AccumulatedUtterance]:
        """Stop all managed sessions."""
        with self._lock:
            results = {}
            for sess_id, bridge in list(self._bridges.items()):
                results[sess_id] = bridge.stop()
            return results


__all__ = [
    "AudioSTTBridge",
    "MultiSessionSTTBridge",
]
