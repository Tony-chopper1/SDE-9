"""
Bounded audio stream buffer with backpressure strategies and telemetry.
Owner: Satwik A (feature/audio-vad) - Week 2 (Days 12-13)

Provides:
- BackpressureStrategy: DROP_OLDEST, DROP_NEWEST, BLOCK
- BufferTelemetry: Snapshot of buffer capacity, occupancy, and dropped statistics
- BoundedAudioBuffer: Thread-safe, bounded frame queue preventing unbounded memory growth.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Iterator, Optional

from packages.audio.exceptions import AudioError
from packages.audio.models import AudioConfig, AudioFrame


class BackpressureStrategy(str, Enum):
    """Strategies to handle buffer full conditions."""
    DROP_OLDEST = "DROP_OLDEST"  # Evict oldest frame in queue to accept new frame (ring-buffer style)
    DROP_NEWEST = "DROP_NEWEST"  # Reject incoming frame, preserving already buffered frames
    BLOCK = "BLOCK"              # Block the producer thread until consumer creates space (or timeout)


class BufferError(AudioError):
    """Raised on buffer operational failures."""

    def __init__(
        self,
        message: str,
        code: str = "AUDIO_BUFFER_ERROR",
        retryable: bool = False,
        details: Optional[dict] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code=code,
            retryable=retryable,
            details_redacted=details,
        )


@dataclass(frozen=True)
class BufferTelemetry:
    """Read-only snapshot of buffer state and drop counters."""
    max_frames: int
    current_frames: int
    current_bytes: int
    current_duration_ms: float
    total_frames_pushed: int
    total_frames_popped: int
    frames_dropped: int
    bytes_dropped: int
    is_closed: bool

    @property
    def utilization_ratio(self) -> float:
        """Fraction of buffer capacity currently occupied (0.0 to 1.0)."""
        if self.max_frames <= 0:
            return 0.0
        return min(1.0, self.current_frames / self.max_frames)


class BoundedAudioBuffer:
    """Thread-safe bounded buffer for discrete AudioFrame streaming.

    Guarantees:
    - Memory footprint is strictly bounded by max_frames * frame_size_bytes.
    - Implements DROP_OLDEST, DROP_NEWEST, and BLOCK backpressure.
    - Thread-safe producer-consumer coordination with threading.Condition.
    - Accurate dropped frames and bytes telemetry.
    """

    def __init__(
        self,
        max_frames: Optional[int] = None,
        max_duration_ms: Optional[float] = None,
        strategy: BackpressureStrategy = BackpressureStrategy.DROP_OLDEST,
        default_frame_duration_ms: int = 20,
    ):
        """Initialize bounded buffer.

        Args:
            max_frames: Maximum number of discrete AudioFrames the buffer can hold.
            max_duration_ms: Optional duration limit; converts to frames if max_frames omitted.
            strategy: BackpressureStrategy on buffer full.
            default_frame_duration_ms: Used to calculate max_frames from max_duration_ms if needed.
        """
        if max_frames is not None and max_frames > 0:
            self._max_frames = int(max_frames)
        elif max_duration_ms is not None and max_duration_ms > 0:
            self._max_frames = max(1, int(max_duration_ms / default_frame_duration_ms))
        else:
            # Default to 50 frames (1.0s of 20ms audio or 1.5s of 30ms audio)
            self._max_frames = 50

        self._strategy = strategy
        self._queue: deque[AudioFrame] = deque()
        self._lock = threading.RLock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)

        self._is_closed = False

        # Counters
        self._total_pushed = 0
        self._total_popped = 0
        self._frames_dropped = 0
        self._bytes_dropped = 0
        self._current_bytes = 0

    @property
    def max_frames(self) -> int:
        return self._max_frames

    @property
    def strategy(self) -> BackpressureStrategy:
        return self._strategy

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._is_closed

    def push(self, frame: AudioFrame, timeout: Optional[float] = None) -> bool:
        """Push an AudioFrame into the buffer according to backpressure policy.

        Args:
            frame: Input AudioFrame.
            timeout: Max seconds to wait when strategy=BLOCK.

        Returns:
            True if frame was accepted/queued, False if dropped or rejected.

        Raises:
            BufferError: If buffer is closed.
        """
        if not isinstance(frame, AudioFrame):
            raise BufferError(f"Expected AudioFrame instance, got {type(frame).__name__}")

        with self._lock:
            if self._is_closed:
                raise BufferError("Cannot push frame: BoundedAudioBuffer is closed.")

            frame_bytes = len(frame.audio_data)

            # Check if buffer is full
            if len(self._queue) >= self._max_frames:
                if self._strategy == BackpressureStrategy.DROP_NEWEST:
                    self._frames_dropped += 1
                    self._bytes_dropped += frame_bytes
                    return False

                elif self._strategy == BackpressureStrategy.DROP_OLDEST:
                    # Evict oldest frame
                    evicted = self._queue.popleft()
                    evicted_bytes = len(evicted.audio_data)
                    self._current_bytes -= evicted_bytes
                    self._frames_dropped += 1
                    self._bytes_dropped += evicted_bytes
                    # Queue now has room for 1 frame

                elif self._strategy == BackpressureStrategy.BLOCK:
                    # Block until space is available or timeout occurs
                    start_time = time.perf_counter()
                    while len(self._queue) >= self._max_frames:
                        if self._is_closed:
                            raise BufferError("Buffer closed while waiting in push BLOCK.")

                        if timeout is not None:
                            elapsed = time.perf_counter() - start_time
                            remaining = timeout - elapsed
                            if remaining <= 0:
                                self._frames_dropped += 1
                                self._bytes_dropped += frame_bytes
                                return False
                            self._not_full.wait(timeout=remaining)
                        else:
                            self._not_full.wait()

            # Space is available: enqueue frame
            self._queue.append(frame)
            self._current_bytes += frame_bytes
            self._total_pushed += 1
            self._not_empty.notify()
            return True

    def pop(self, timeout: Optional[float] = None) -> Optional[AudioFrame]:
        """Pop the oldest AudioFrame from the buffer.

        Args:
            timeout: Max seconds to wait for a frame. If None, returns immediately (non-blocking).

        Returns:
            AudioFrame, or None if buffer is empty.
        """
        with self._lock:
            if len(self._queue) == 0:
                if timeout is None or timeout <= 0 or self._is_closed:
                    return None

                # Wait for an incoming frame
                start_time = time.perf_counter()
                while len(self._queue) == 0:
                    if self._is_closed:
                        return None
                    elapsed = time.perf_counter() - start_time
                    remaining = timeout - elapsed
                    if remaining <= 0:
                        return None
                    self._not_empty.wait(timeout=remaining)

            if len(self._queue) == 0:
                return None

            frame = self._queue.popleft()
            self._current_bytes -= len(frame.audio_data)
            self._total_popped += 1
            self._not_full.notify()
            return frame

    def clear(self) -> None:
        """Clear all buffered frames."""
        with self._lock:
            self._queue.clear()
            self._current_bytes = 0
            self._not_full.notify_all()

    def close(self) -> None:
        """Close buffer, waking any blocked threads."""
        with self._lock:
            self._is_closed = True
            self._not_empty.notify_all()
            self._not_full.notify_all()

    def get_telemetry(self) -> BufferTelemetry:
        """Return snapshot telemetry of buffer status and drops."""
        with self._lock:
            curr_frames = len(self._queue)
            curr_dur_ms = sum(f.frame_duration_ms for f in self._queue)
            return BufferTelemetry(
                max_frames=self._max_frames,
                current_frames=curr_frames,
                current_bytes=self._current_bytes,
                current_duration_ms=float(curr_dur_ms),
                total_frames_pushed=self._total_pushed,
                total_frames_popped=self._total_popped,
                frames_dropped=self._frames_dropped,
                bytes_dropped=self._bytes_dropped,
                is_closed=self._is_closed,
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def stream(self, poll_interval: float = 0.01) -> Iterator[AudioFrame]:
        """Yield frames as they become available until the buffer is closed and empty."""
        while True:
            with self._lock:
                if self._is_closed and len(self._queue) == 0:
                    break
            frame = self.pop(timeout=poll_interval)
            if frame is not None:
                yield frame
