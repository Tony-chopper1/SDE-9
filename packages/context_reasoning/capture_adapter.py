"""
Opt-in Screen Capture Adapter for AI Voice Co-Pilot.

Enforces privacy-first opt-in policies, sampling frequency (FPS) limits,
and dimension/byte size bounds using purely synthetic test frames.
No real screen captures or sensitive user data are ever recorded or committed.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from packages.context_reasoning.exceptions import (
    CaptureDisabledError,
    FrameSizeLimitError,
    SamplingRateLimitError,
)
from packages.context_reasoning.models import CaptureConfig, ScreenContext, WindowContext


class CaptureAdapter:
    """
    Manages screen frame capture lifecycle with strict privacy and resource controls.

    Features:
    - Opt-in by default (`capture_enabled = False`).
    - Enforced sampling rate limits (`max_fps`).
    - Enforced dimension and byte size constraints (`max_width`, `max_height`, `max_bytes`).
    - Purely synthetic deterministic frame generation (zero external dependencies).
    - Observable telemetry and metrics collection.
    """

    def __init__(self, config: Optional[CaptureConfig] = None) -> None:
        """
        Initialize the capture adapter.

        Args:
            config: Optional configuration specifying limits and initial privacy state.
        """
        self.config = config or CaptureConfig(capture_enabled=False)
        self._last_capture_timestamp: float = 0.0
        self._last_frame: Optional[ScreenContext] = None
        self._capture_count: int = 0
        self._total_bytes: int = 0

    def enable(self) -> None:
        """Opt in to screen frame capture."""
        self.config.capture_enabled = True

    def disable(self) -> None:
        """Opt out and disable screen frame capture."""
        self.config.capture_enabled = False

    def is_enabled(self) -> bool:
        """Return True if screen frame capture is currently permitted."""
        return self.config.capture_enabled

    def capture_frame(
        self,
        width: int = 1280,
        height: int = 720,
        pattern: str = "test_bars",
        visible_text: Optional[str] = None,
        active_window: Optional[WindowContext] = None,
        force: bool = False,
        throttle_cached: bool = False,
    ) -> ScreenContext:
        """
        Capture a synthetic screen frame under enforced privacy, sampling, and size limits.

        Args:
            width: Requested horizontal resolution in pixels.
            height: Requested vertical resolution in pixels.
            pattern: Synthetic pattern identifier.
            visible_text: Simulated code or text visible on screen.
            active_window: Associated window context.
            force: If True, bypasses opt-in check (for unit testing only).
            throttle_cached: If True and sampling frequency is exceeded, returns cached last frame
                             instead of raising SamplingRateLimitError.

        Returns:
            Generated synthetic ScreenContext.

        Raises:
            CaptureDisabledError: If capture is disabled and force is False.
            SamplingRateLimitError: If capture rate exceeds configured max_fps.
            FrameSizeLimitError: If frame dimensions or byte size exceed configured maximums.
        """
        # 1. Privacy Opt-In Check
        if not self.config.capture_enabled and not force:
            raise CaptureDisabledError(
                "Screen context capture is disabled by default. "
                "Must explicitly call enable() to opt into screen reasoning."
            )

        now = time.time()
        min_interval = 1.0 / self.config.max_fps

        # 2. Sampling Frequency Check
        if self._last_capture_timestamp > 0 and (now - self._last_capture_timestamp) < min_interval:
            if throttle_cached and self._last_frame is not None:
                return self._last_frame
            time_since_last = now - self._last_capture_timestamp
            raise SamplingRateLimitError(
                f"Capture request exceeded sampling limit of {self.config.max_fps} FPS. "
                f"Minimum interval is {min_interval:.3f}s; elapsed time was {time_since_last:.3f}s."
            )

        # 3. Dimension Bounds Check
        final_width = width
        final_height = height

        if width > self.config.max_width or height > self.config.max_height:
            if self.config.downscale_on_overflow:
                # Downscale proportionally while respecting bounds
                scale_w = self.config.max_width / width
                scale_h = self.config.max_height / height
                scale = min(scale_w, scale_h)
                final_width = max(64, int(width * scale))
                final_height = max(64, int(height * scale))
            else:
                raise FrameSizeLimitError(
                    f"Frame dimensions ({width}x{height}) exceed maximum allowed "
                    f"({self.config.max_width}x{self.config.max_height})."
                )

        # 4. Generate Synthetic Frame
        frame = ScreenContext.create_synthetic(
            width=final_width,
            height=final_height,
            capture_enabled=self.config.capture_enabled or force,
            pattern=pattern,
            visible_text=visible_text,
            active_window=active_window,
        )

        # 5. Byte Size Limit Check
        byte_size = len(frame.image_data) if frame.image_data else 0
        if byte_size > self.config.max_bytes:
            raise FrameSizeLimitError(
                f"Frame byte size ({byte_size} bytes) exceeds maximum limit of "
                f"{self.config.max_bytes} bytes."
            )

        # 6. Update Telemetry
        self._last_capture_timestamp = now
        self._last_frame = frame
        self._capture_count += 1
        self._total_bytes += byte_size

        return frame

    def get_metrics(self) -> Dict[str, Any]:
        """Return operational telemetry metrics for observability."""
        return {
            "capture_enabled": self.config.capture_enabled,
            "max_fps": self.config.max_fps,
            "max_dimensions": f"{self.config.max_width}x{self.config.max_height}",
            "max_bytes": self.config.max_bytes,
            "total_captures": self._capture_count,
            "total_bytes_captured": self._total_bytes,
            "last_capture_timestamp": self._last_capture_timestamp,
        }

    def reset(self) -> None:
        """Reset internal metrics and state."""
        self._last_capture_timestamp = 0.0
        self._last_frame = None
        self._capture_count = 0
        self._total_bytes = 0
