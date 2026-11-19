"""
Bounded Exponential Backoff Retry Handler for STT Provider Calls.

Provides configurable retry loops with exponential backoff, jitter,
and timeout boundaries to prevent cascading failures.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Optional, Set, Type

from packages.speech_to_text.exceptions import (
    STTError,
    STTTimeoutError,
    normalize_stt_exception,
)


class BoundedRetryHandler:
    """Executes callables with bounded retries, exponential backoff, and error normalization.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        base_backoff_sec: Initial backoff duration in seconds (default: 0.05).
        max_backoff_sec: Upper limit for backoff duration (default: 1.0).
        backoff_multiplier: Multiplier per successive attempt (default: 2.0).
        jitter: Whether to add random jitter to prevent thundering herd (default: True).
        timeout_sec: Timeout per individual execution attempt (default: 5.0).
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_backoff_sec: float = 0.05,
        max_backoff_sec: float = 1.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
        timeout_sec: float = 5.0,
        retriable_exceptions: Optional[Set[Type[Exception]]] = None,
    ) -> None:
        self.max_retries = max(0, max_retries)
        self.base_backoff_sec = base_backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.timeout_sec = timeout_sec
        self.retriable_exceptions = retriable_exceptions or {
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
            STTTimeoutError,
        }

    def is_retriable(self, exc: Exception) -> bool:
        """Determine whether an exception qualifies for automatic retry."""
        if isinstance(exc, tuple(self.retriable_exceptions)):
            return True
        exc_str = str(exc).lower()
        if "timeout" in exc_str or "temporar" in exc_str or "connection" in exc_str or "503" in exc_str:
            return True
        return False

    def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute *func* with bounded retries and error normalization.

        Raises:
            STTError: Normalized error envelope on final exhaustion.
        """
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt <= self.max_retries:
            start_time = time.time()
            try:
                # Execute target function
                return func(*args, **kwargs)
            except Exception as exc:
                last_exception = exc
                attempt += 1

                # If exhausted or not retriable, fail immediately
                if attempt > self.max_retries or not self.is_retriable(exc):
                    normalized = normalize_stt_exception(exc)
                    normalized.details["total_attempts"] = attempt
                    raise normalized from exc

                # Compute exponential backoff with optional jitter
                backoff = min(
                    self.max_backoff_sec,
                    self.base_backoff_sec * (self.backoff_multiplier ** (attempt - 1)),
                )
                if self.jitter:
                    backoff = backoff * (0.5 + random.random() * 0.5)

                time.sleep(backoff)

        # Fallback (should not be reached)
        raise normalize_stt_exception(last_exception or Exception("Max retries exceeded"))
