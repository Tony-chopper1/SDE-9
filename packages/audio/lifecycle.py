"""
Stream lifecycle controller, state machine, and lifecycle exceptions.
Owner: Satwik A (feature/audio-vad) - Week 2 (Days 10-11)

Provides:
- StreamState: IDLE, RUNNING, PAUSED, STOPPED, ERROR
- StreamLifecycleError, InvalidStateTransitionError
- StreamLifecycleController: Manages start, pause, resume, stop lifecycle
  over AudioDeviceAdapter and AudioSource.
"""
from __future__ import annotations

from enum import Enum
import threading
import time
import uuid
from typing import Any, Callable, Iterator, Optional

from packages.audio.device import AudioDeviceAdapter, DeviceInfo, PermissionState
from packages.audio.events import AudioEventType
from packages.audio.exceptions import AudioError, DevicePermissionError
from packages.audio.mock_mic import AudioSource
from packages.audio.models import AudioConfig, AudioFrame, EventEnvelope


class StreamState(str, Enum):
    """Audio stream lifecycle states."""
    IDLE = "IDLE"          # Created, device ready, not producing frames
    READY = "IDLE"         # Convenience alias for IDLE (initialized and ready to start)
    RUNNING = "RUNNING"    # Active, capturing/producing audio frames
    PAUSED = "PAUSED"      # Temporarily paused, source open but read muted/suspended
    STOPPED = "STOPPED"    # Completed or stopped, source closed, resources freed
    ERROR = "ERROR"        # Error encountered, safely halted
    DEVICE_LOST = "DEVICE_LOST"  # Capture device disconnected/lost during active session


class StreamLifecycleError(AudioError):
    """Base exception for stream lifecycle errors."""

    def __init__(
        self,
        message: str,
        code: str = "AUDIO_LIFECYCLE_ERROR",
        retryable: bool = False,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code=code,
            retryable=retryable,
            details_redacted=details,
        )


class InvalidStateTransitionError(StreamLifecycleError):
    """Raised when an invalid lifecycle state transition is attempted."""

    def __init__(self, from_state: StreamState, to_action: str):
        super().__init__(
            message=f"Cannot perform action '{to_action}' while stream is in state '{from_state.value}'.",
            code="AUDIO_INVALID_STATE_TRANSITION",
            retryable=False,
            details={"current_state": from_state.value, "attempted_action": to_action},
        )
        self.from_state = from_state
        self.to_action = to_action


class StreamLifecycleController:
    """Manages audio capture lifecycle states and resources safely.

    Valid State Transitions:
    - start():   IDLE -> RUNNING  (or STOPPED -> RUNNING if restarted)
    - pause():   RUNNING -> PAUSED
    - resume():  PAUSED -> RUNNING
    - stop():    RUNNING -> STOPPED, PAUSED -> STOPPED, IDLE -> STOPPED, ERROR -> STOPPED
    """

    def __init__(
        self,
        device_adapter: AudioDeviceAdapter,
        config: Optional[AudioConfig] = None,
        source_factory: Optional[Callable[[AudioConfig], AudioSource]] = None,
        session_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        event_dispatcher: Optional[Any] = None,
        buffer: Optional[Any] = None,
        pipeline: Optional[Any] = None,
    ):
        self._adapter = device_adapter
        self._config = config or AudioConfig()
        self._source_factory = source_factory
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
        self.correlation_id = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
        self._pipeline = pipeline
        self._event_dispatcher = event_dispatcher or (getattr(pipeline, "dispatcher", None) if pipeline else None)
        self._buffer = buffer
        self._state = StreamState.IDLE
        self._source: Optional[AudioSource] = None
        self._lock = threading.RLock()
        self._is_cancelled = False
        self._active_device_id: Optional[str] = None

        # Telemetry & stats
        self._frames_produced = 0
        self._frames_paused_dropped = 0
        self._error: Optional[Exception] = None

    @property
    def state(self) -> StreamState:
        """Current stream lifecycle state."""
        with self._lock:
            return self._state

    @property
    def is_running(self) -> bool:
        """True if actively capturing frames."""
        with self._lock:
            return self._state == StreamState.RUNNING

    @property
    def is_paused(self) -> bool:
        """True if stream is paused."""
        with self._lock:
            return self._state == StreamState.PAUSED

    @property
    def is_cancelled(self) -> bool:
        """True if capture has been cancelled."""
        with self._lock:
            return self._is_cancelled

    @property
    def is_device_lost(self) -> bool:
        """True if capture device was lost during an active session."""
        with self._lock:
            return self._state == StreamState.DEVICE_LOST

    @property
    def active_device_id(self) -> Optional[str]:
        """Device ID of currently active capture device."""
        with self._lock:
            return self._active_device_id

    @property
    def config(self) -> AudioConfig:
        return self._config

    @property
    def frames_produced(self) -> int:
        return self._frames_produced

    @property
    def frames_paused_dropped(self) -> int:
        return self._frames_paused_dropped

    @property
    def buffer(self) -> Optional[Any]:
        return self._buffer

    @property
    def pipeline(self) -> Optional[Any]:
        return self._pipeline

    @property
    def event_dispatcher(self) -> Optional[Any]:
        return self._event_dispatcher

    @property
    def capture_state(self) -> str:
        """UI-friendly capture state string derived from current StreamState.

        Mapping:
        - RUNNING -> 'recording'
        - PAUSED -> 'paused'
        - IDLE / STOPPED -> 'idle'
        - DEVICE_LOST / ERROR -> 'error'
        """
        with self._lock:
            if self._state == StreamState.RUNNING:
                return "recording"
            elif self._state == StreamState.PAUSED:
                return "paused"
            elif self._state in (StreamState.IDLE, StreamState.STOPPED):
                return "idle"
            else:
                return "error"

    def start(self) -> None:
        """Start capturing audio.

        Allowed from: IDLE, STOPPED.
        Transitions to: RUNNING.

        Raises:
            InvalidStateTransitionError: If called while RUNNING or PAUSED.
            DevicePermissionError: If microphone permission is denied or unavailable.
        """
        with self._lock:
            if self._state == StreamState.RUNNING:
                raise InvalidStateTransitionError(self._state, "start")
            if self._state == StreamState.PAUSED:
                raise InvalidStateTransitionError(self._state, "start")

            # Check device permission
            perm = self._adapter.get_permission_state()
            if perm == PermissionState.DENIED:
                self._state = StreamState.ERROR
                raise DevicePermissionError(
                    "Cannot start audio stream: microphone permission is denied.",
                    code="AUDIO_PERMISSION_DENIED",
                )
            if perm == PermissionState.UNAVAILABLE:
                self._state = StreamState.ERROR
                raise DevicePermissionError(
                    "Cannot start audio stream: microphone hardware is unavailable.",
                    code="AUDIO_DEVICE_UNAVAILABLE",
                )
            if perm == PermissionState.PROMPT:
                self._state = StreamState.ERROR
                raise DevicePermissionError(
                    "Cannot start audio stream: microphone permission has not been requested/granted.",
                    code="AUDIO_PERMISSION_PROMPT",
                )

            try:
                # Open source
                if self._source_factory:
                    self._source = self._source_factory(self._config)
                else:
                    self._source = self._adapter.create_source(self._config)

                self._source.open()
                self._state = StreamState.RUNNING
                self._is_cancelled = False
                try:
                    dev = self._adapter.get_selected_device()
                    self._active_device_id = dev.device_id
                except Exception:
                    self._active_device_id = None
                self._error = None

                # Emit stream start event if dispatcher is configured
                if self._event_dispatcher is not None and hasattr(self._event_dispatcher, "dispatch"):
                    try:
                        env = EventEnvelope.create(
                            event_type=AudioEventType.STREAM_START.value,
                            session_id=self.session_id,
                            correlation_id=self.correlation_id,
                            payload={
                                "state": self.capture_state,
                                "lifecycle_state": self._state.value,
                                "device_id": self._active_device_id,
                            },
                        )
                        self._event_dispatcher.dispatch(env)
                    except Exception:
                        pass
            except Exception as e:
                self._state = StreamState.ERROR
                self._error = e
                self._cleanup_resources()
                raise

    def pause(self) -> None:
        """Pause audio capture.

        Allowed from: RUNNING.
        Transitions to: PAUSED.

        Raises:
            InvalidStateTransitionError: If not in RUNNING state.
        """
        with self._lock:
            if self._state != StreamState.RUNNING:
                raise InvalidStateTransitionError(self._state, "pause")
            self._state = StreamState.PAUSED

    def resume(self) -> None:
        """Resume audio capture after being paused.

        Allowed from: PAUSED.
        Transitions to: RUNNING.

        Raises:
            InvalidStateTransitionError: If not in PAUSED state.
        """
        with self._lock:
            if self._state != StreamState.PAUSED:
                raise InvalidStateTransitionError(self._state, "resume")
            self._state = StreamState.RUNNING

    def stop(self) -> None:
        """Stop audio capture and release resources safely.

        Allowed from: any state (idempotent when already STOPPED).
        Transitions to: STOPPED.
        """
        with self._lock:
            if self._state == StreamState.STOPPED:
                return
            prev_state = self._state
            self._state = StreamState.STOPPED
            self._cleanup_resources()

            # Emit stream stop event if dispatcher is configured
            if self._event_dispatcher is not None and hasattr(self._event_dispatcher, "dispatch"):
                try:
                    env = EventEnvelope.create(
                        event_type=AudioEventType.STREAM_STOP.value,
                        session_id=self.session_id,
                        correlation_id=self.correlation_id,
                        payload={
                            "state": self.capture_state,
                            "lifecycle_state": self._state.value,
                            "previous_state": prev_state.value,
                            "reason": "normal_stop",
                        },
                    )
                    self._event_dispatcher.dispatch(env)
                except Exception:
                    pass

    def _cleanup_resources(self) -> None:
        """Safely close underlying source and release resources without throwing."""
        if self._source is not None:
            try:
                self._source.close()
            except Exception:
                pass
            finally:
                self._source = None

    def handle_device_loss(self, reason: str = "device_disconnected") -> bool:
        """Trigger device-loss state transition, resource release, and event dispatch.

        Returns:
            True if transitioned to DEVICE_LOST, False if already device lost or cancelled.
        """
        with self._lock:
            if self._state == StreamState.DEVICE_LOST or self._is_cancelled:
                return False
            self._handle_device_loss(reason=reason)
            return True

    def _handle_device_loss(self, reason: str = "device_disconnected") -> None:
        """Internal helper to transition to DEVICE_LOST, cleanup source, and dispatch event."""
        if self._state == StreamState.DEVICE_LOST or self._is_cancelled:
            return
        lost_device_id = self._active_device_id
        self._state = StreamState.DEVICE_LOST
        self._cleanup_resources()

        # Emit device loss event through pipeline if attached, else dispatcher
        if self._pipeline is not None and hasattr(self._pipeline, "handle_device_loss"):
            try:
                self._pipeline.handle_device_loss(device_id=lost_device_id, reason=reason)
            except Exception:
                pass
        elif self._event_dispatcher is not None and hasattr(self._event_dispatcher, "dispatch"):
            try:
                env = EventEnvelope.create(
                    event_type=AudioEventType.DEVICE_LOST.value,
                    session_id=self.session_id,
                    correlation_id=self.correlation_id,
                    payload={
                        "state": "DEVICE_LOST",
                        "device_id": lost_device_id,
                        "reason": reason,
                        "total_frames_before_loss": self._frames_produced,
                    },
                )
                self._event_dispatcher.dispatch(env)
            except Exception:
                pass

    def reconnect(
        self,
        target_device_id: Optional[str] = None,
        allow_fallback: bool = True,
    ) -> bool:
        """Attempt to reconnect to the original or specified audio device, or fallback.

        Guarantees:
        - Only reconnects if currently in DEVICE_LOST or PAUSED state.
        - Preserves existing session_id and correlation_id.
        - Avoids duplicate recovery events.
        - Transitions state to RUNNING and attaches newly opened source.

        Args:
            target_device_id: Device ID to connect to (defaults to previous active device ID).
            allow_fallback: Whether to fallback to another available device if target is unavailable.

        Returns:
            True if reconnected successfully, False if no device is available.
        """
        with self._lock:
            if self._is_cancelled:
                return False
            if self._state not in (StreamState.DEVICE_LOST, StreamState.PAUSED):
                return False

            desired_id = target_device_id or self._active_device_id
            chosen_device: Optional[DeviceInfo] = None
            is_fallback = False

            # 1. Try desired device if available
            if desired_id:
                try:
                    devices = self._adapter.list_devices()
                    for d in devices:
                        if d.device_id == desired_id and d.is_available:
                            chosen_device = d
                            break
                except Exception:
                    chosen_device = None

            # 2. Try fallback if desired device is unavailable
            if chosen_device is None and allow_fallback:
                try:
                    if hasattr(self._adapter, "find_fallback_device"):
                        chosen_device = self._adapter.find_fallback_device(exclude_id=desired_id)
                    else:
                        for d in self._adapter.list_devices():
                            if d.is_available and d.device_id != desired_id:
                                chosen_device = d
                                break
                    if chosen_device is not None:
                        is_fallback = True
                except Exception:
                    chosen_device = None

            if chosen_device is None:
                return False

            # 3. Select device and create new source
            try:
                self._adapter.select_device(chosen_device.device_id)
                if self._source_factory:
                    new_source = self._source_factory(self._config)
                else:
                    new_source = self._adapter.create_source(self._config)

                new_source.open()
                self._cleanup_resources()
                self._source = new_source
                self._active_device_id = chosen_device.device_id
                self._state = StreamState.RUNNING
                self._error = None

                # 4. Dispatch recovery event
                if self._pipeline is not None and hasattr(self._pipeline, "handle_device_recovery"):
                    try:
                        self._pipeline.handle_device_recovery(
                            device_id=chosen_device.device_id,
                            is_fallback=is_fallback,
                        )
                    except Exception:
                        pass
                elif self._event_dispatcher is not None and hasattr(self._event_dispatcher, "dispatch"):
                    try:
                        env = EventEnvelope.create(
                            event_type=AudioEventType.DEVICE_RECOVERED.value,
                            session_id=self.session_id,
                            correlation_id=self.correlation_id,
                            payload={
                                "state": "DEVICE_RECOVERED",
                                "device_id": chosen_device.device_id,
                                "is_fallback": is_fallback,
                                "session_id": self.session_id,
                                "correlation_id": self.correlation_id,
                            },
                        )
                        self._event_dispatcher.dispatch(env)
                    except Exception:
                        pass

                return True
            except Exception as e:
                self._error = e
                return False

    def cancel(self, reason: str = "user_cancelled") -> None:
        """Atomically halt capture, cancel buffer, pipeline, and transition to STOPPED.

        Guarantees:
        - Immediately stops frame production.
        - Closes active source and releases hardware resources.
        - Clears and closes attached BoundedAudioBuffer, waking waiting consumer threads.
        - Cancels attached AudioSessionPipeline, bounding active speech if speaking.
        - Transitions lifecycle state to terminal STOPPED state.
        - Safe and idempotent on repeated calls.
        - Thread-safe under RLock.
        """
        with self._lock:
            if self._is_cancelled:
                return
            self._is_cancelled = True
            self._state = StreamState.STOPPED

            # 1. Close source
            self._cleanup_resources()

            # 2. Cancel buffer if attached
            if self._buffer is not None and hasattr(self._buffer, "cancel"):
                try:
                    self._buffer.cancel()
                except Exception:
                    pass

            # 3. Cancel pipeline if attached
            if self._pipeline is not None and hasattr(self._pipeline, "cancel"):
                try:
                    self._pipeline.cancel(reason=reason)
                except Exception:
                    pass
            elif self._event_dispatcher is not None and hasattr(self._event_dispatcher, "dispatch"):
                try:
                    env = EventEnvelope.create(
                        event_type=AudioEventType.STREAM_CANCELLED.value,
                        session_id=self.session_id,
                        correlation_id=self.correlation_id,
                        payload={
                            "state": "CANCELLED",
                            "reason": reason,
                            "total_frames_processed": self._frames_produced,
                        },
                    )
                    self._event_dispatcher.dispatch(env)
                except Exception:
                    pass

    def read_frame(self) -> Optional[AudioFrame]:
        """Read the next audio frame from the active stream.

        - When cancelled, stopped, or idle: returns None.
        - When DEVICE_LOST: returns None (caller may attempt reconnect()).
        - When PAUSED: advances source if active to discard/count, returning None while paused.
        - When RUNNING: verifies device availability; reads next frame from source.
          If device becomes unavailable or source raises an access error, transitions to
          DEVICE_LOST and returns None without raising an uncaught exception.

        Raises:
            StreamLifecycleError: If stream is in ERROR state.
        """
        with self._lock:
            if self._is_cancelled:
                return None

            if self._state == StreamState.ERROR:
                raise StreamLifecycleError(
                    f"Cannot read frame: stream is in ERROR state ({self._error}).",
                    code="AUDIO_STREAM_ERROR_STATE",
                )

            if self._state in (StreamState.IDLE, StreamState.STOPPED, StreamState.DEVICE_LOST):
                return None

            # Verify active device physical availability if supported
            if hasattr(self._adapter, "is_selected_device_available"):
                try:
                    if not self._adapter.is_selected_device_available():
                        self._handle_device_loss(reason="device_unavailable")
                        return None
                except Exception as e:
                    self._handle_device_loss(reason=f"device_check_error: {e}")
                    return None

            if self._state == StreamState.PAUSED:
                # Discard frames from source while paused so queue doesn't stall
                if self._source and self._source.is_active:
                    try:
                        discarded = self._source.read_frame()
                        if discarded is None:
                            self.stop()
                            return None
                        self._frames_paused_dropped += 1
                    except Exception as e:
                        self._handle_device_loss(reason=f"read_error_paused: {e}")
                        return None
                return None

            # RUNNING state
            if not self._source or not self._source.is_active:
                self.stop()
                return None

            try:
                frame = self._source.read_frame()
            except Exception as e:
                # Hardware disconnected during read
                self._handle_device_loss(reason=f"source_read_error: {e}")
                return None

            if frame is None:
                # EOF or unexpected device disconnect
                if hasattr(self._adapter, "is_selected_device_available"):
                    try:
                        if not self._adapter.is_selected_device_available():
                            self._handle_device_loss(reason="device_disconnected_at_eof")
                            return None
                    except Exception:
                        pass
                self.stop()
                return None

            self._frames_produced += 1
            return frame

    def stream(self) -> Iterator[AudioFrame]:
        """Generator yielding frames while running. Terminates on stop, cancellation, or EOF."""
        while True:
            with self._lock:
                if self._is_cancelled or self._state in (StreamState.STOPPED, StreamState.IDLE, StreamState.ERROR):
                    break
                is_dev_lost = (self._state == StreamState.DEVICE_LOST)

            if is_dev_lost:
                # Briefly sleep to allow reconnection rather than busy-loop spinning
                time.sleep(self._config.frame_duration_ms / 1000.0)
                continue

            frame = self.read_frame()
            if frame is not None:
                yield frame
            else:
                with self._lock:
                    if self._is_cancelled or self._state in (StreamState.STOPPED, StreamState.IDLE, StreamState.ERROR):
                        break
                    if self._state in (StreamState.PAUSED, StreamState.DEVICE_LOST):
                        time.sleep(self._config.frame_duration_ms / 1000.0)

    def __enter__(self) -> StreamLifecycleController:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
