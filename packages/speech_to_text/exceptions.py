"""
Normalized Error Hierarchy for Speech-to-Text (STT) Module.

Ensures no raw, provider-specific, or network exceptions leak into client code.
Conforms strictly to the SDK-9 Integration Contract error envelope format:
`{"error": str, "code": str, "timestamp": float, "details": dict}`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class STTError(Exception):
    """Base exception for all normalized Speech-to-Text errors."""

    def __init__(
        self,
        message: str,
        code: str = "STT_ERROR",
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.original_exception = original_exception
        self.timestamp = time.time()

    def to_envelope(self) -> Dict[str, Any]:
        """Serialize into standardized SDK-9 integration error envelope."""
        return {
            "error": self.message,
            "code": self.code,
            "timestamp": self.timestamp,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code='{self.code}', message='{self.message}')"


class STTTimeoutError(STTError):
    """Raised when transcription times out."""

    def __init__(
        self,
        message: str = "Speech-to-text operation timed out.",
        timeout_seconds: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        extra = details or {}
        if timeout_seconds is not None:
            extra["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=message,
            code="STT_TIMEOUT",
            details=extra,
            original_exception=original_exception,
        )


class STTProviderError(STTError):
    """Raised when an STT engine or provider returns a failure."""

    def __init__(
        self,
        message: str,
        provider_name: str = "mock",
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        extra = details or {}
        extra["provider"] = provider_name
        if status_code is not None:
            extra["status_code"] = status_code
        super().__init__(
            message=message,
            code="STT_PROVIDER_ERROR",
            details=extra,
            original_exception=original_exception,
        )


class STTConnectionError(STTError):
    """Raised when communication with an STT service fails or disconnects."""

    def __init__(
        self,
        message: str = "Connection to speech recognition provider failed.",
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message=message,
            code="STT_CONNECTION_ERROR",
            details=details,
            original_exception=original_exception,
        )


class STTRateLimitError(STTError):
    """Raised when provider rate limits are exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded for transcription requests.",
        retry_after_sec: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ) -> None:
        extra = details or {}
        if retry_after_sec is not None:
            extra["retry_after_sec"] = retry_after_sec
        super().__init__(
            message=message,
            code="STT_RATE_LIMIT",
            details=extra,
            original_exception=original_exception,
        )


def normalize_stt_exception(
    exc: Exception,
    provider_name: str = "mock",
) -> STTError:
    """Normalize arbitrary external or system exceptions into a typed STTError.

    Ensures zero raw third-party exception types leak to callers.
    """
    if isinstance(exc, STTError):
        return exc

    exc_str = str(exc)
    exc_type = type(exc).__name__

    if isinstance(exc, TimeoutError) or "timeout" in exc_str.lower() or "timed out" in exc_str.lower():
        return STTTimeoutError(
            message=f"Transcription timed out: {exc_str}",
            details={"original_error_type": exc_type},
            original_exception=exc,
        )

    if isinstance(exc, (ConnectionError, ConnectionResetError, BrokenPipeError)) or "connection" in exc_str.lower():
        return STTConnectionError(
            message=f"STT stream connection lost: {exc_str}",
            details={"original_error_type": exc_type},
            original_exception=exc,
        )

    return STTProviderError(
        message=f"Transcription provider failed: {exc_str}",
        provider_name=provider_name,
        details={"original_error_type": exc_type},
        original_exception=exc,
    )
