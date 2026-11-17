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
from typing import Callable, Iterator, Optional

from packages.audio.device import AudioDeviceAdapter, PermissionState
from packages.audio.exceptions import AudioError, DevicePermissionError
from packages.audio.mock_mic import AudioSource
from packages.audio.models import AudioConfig, AudioFrame


class StreamState(str, Enum):
    """Audio stream lifecycle states."""
    IDLE = "IDLE"          # Created, device ready, not producing frames
    READY = "IDLE"         # Convenience alias for IDLE (initialized and ready to start)
    RUNNING = "RUNNING"    # Active, capturing/producing audio frames
    PAUSED = "PAUSED"      # Temporarily paused, source open but read muted/suspended
    STOPPED = "STOPPED"    # Completed or stopped, source closed, resources freed
    ERROR = "ERROR"        # Error encountered, safely halted


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
    ):
        self._adapter = device_adapter
        self._config = config or AudioConfig()
        self._source_factory = source_factory
        self._state = StreamState.IDLE
        self._source: Optional[AudioSource] = None
        self._lock = threading.RLock()

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
    def config(self) -> AudioConfig:
        return self._config

    @property
    def frames_produced(self) -> int:
        return self._frames_produced

    @property
    def frames_paused_dropped(self) -> int:
        return self._frames_paused_dropped

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
                self._error = None
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
            self._state = StreamState.STOPPED
            self._cleanup_resources()

    def _cleanup_resources(self) -> None:
        """Safely close underlying source and release resources without throwing."""
        if self._source is not None:
            try:
                self._source.close()
            except Exception:
                pass
            finally:
                self._source = None

    def read_frame(self) -> Optional[AudioFrame]:
        """Read the next audio frame from the active stream.

        - When RUNNING: returns next AudioFrame from source (or None on EOF).
        - When PAUSED: advances source if active to discard/count, returning None while paused.
        - When STOPPED or IDLE: returns None.

        Raises:
            StreamLifecycleError: If stream is in ERROR state.
        """
        with self._lock:
            if self._state == StreamState.ERROR:
                raise StreamLifecycleError(
                    f"Cannot read frame: stream is in ERROR state ({self._error}).",
                    code="AUDIO_STREAM_ERROR_STATE",
                )

            if self._state in (StreamState.IDLE, StreamState.STOPPED):
                return None

            if self._state == StreamState.PAUSED:
                # Discard frames from source while paused so queue doesn't stall
                if self._source and self._source.is_active:
                    discarded = self._source.read_frame()
                    if discarded is None:
                        self.stop()
                        return None
                    self._frames_paused_dropped += 1
                return None

            # RUNNING state
            if not self._source or not self._source.is_active:
                self.stop()
                return None

            frame = self._source.read_frame()
            if frame is None:
                self.stop()
                return None

            self._frames_produced += 1
            return frame

    def stream(self) -> Iterator[AudioFrame]:
        """Generator yielding frames while running. Terminifies on stop or EOF."""
        while True:
            with self._lock:
                if self._state in (StreamState.STOPPED, StreamState.IDLE, StreamState.ERROR):
                    break
            frame = self.read_frame()
            if frame is not None:
                yield frame
            else:
                with self._lock:
                    if self._state == StreamState.PAUSED:
                        # Brief sleep when paused to avoid busy-wait spinning
                        time.sleep(self._config.frame_duration_ms / 1000.0)
                    elif self._state in (StreamState.STOPPED, StreamState.IDLE, StreamState.ERROR):
                        break

    def __enter__(self) -> StreamLifecycleController:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
