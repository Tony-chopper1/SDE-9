"""
Typed exception classes for the Audio & VAD module.

Conforms to the SDK-9 Error Envelope defined in docs/integration-contracts.md:
- code
- message_safe_for_user
- retryable
- correlation_id
- details_redacted
"""
from typing import Any, Dict, Optional


class AudioError(Exception):
    """Base exception for all Audio & VAD module errors."""

    def __init__(
        self,
        message_safe_for_user: str,
        code: str = "AUDIO_GENERAL_ERROR",
        retryable: bool = False,
        correlation_id: Optional[str] = None,
        details_redacted: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message_safe_for_user)
        self.code = code
        self.message_safe_for_user = message_safe_for_user
        self.retryable = retryable
        self.correlation_id = correlation_id
        self.details_redacted = details_redacted or {}

    def to_envelope(self) -> Dict[str, Any]:
        """Serialize exception to standard SDK-9 error envelope."""
        return {
            "code": self.code,
            "message_safe_for_user": self.message_safe_for_user,
            "retryable": self.retryable,
            "correlation_id": self.correlation_id,
            "details_redacted": self.details_redacted,
        }


class AudioConfigError(AudioError):
    """Raised when an audio configuration parameter is invalid or unsupported."""

    def __init__(
        self,
        message: str,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code="AUDIO_CONFIG_INVALID",
            retryable=False,
            correlation_id=correlation_id,
            details_redacted=details,
        )


class AudioFrameValidationError(AudioError):
    """Raised when an audio frame fails payload, length, or sequence validation."""

    def __init__(
        self,
        message: str,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code="AUDIO_FRAME_INVALID",
            retryable=False,
            correlation_id=correlation_id,
            details_redacted=details,
        )


class AudioSourceError(AudioError):
    """Raised when an audio source encounters operational or lifecycle errors."""

    def __init__(
        self,
        message: str,
        retryable: bool = False,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code="AUDIO_SOURCE_ERROR",
            retryable=retryable,
            correlation_id=correlation_id,
            details_redacted=details,
        )


class VADError(AudioError):
    """Raised when Voice Activity Detection processing fails."""

    def __init__(
        self,
        message: str,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message_safe_for_user=message,
            code="AUDIO_VAD_ERROR",
            retryable=False,
            correlation_id=correlation_id,
            details_redacted=details,
        )
