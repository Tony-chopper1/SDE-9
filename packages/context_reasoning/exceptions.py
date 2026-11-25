"""
Exceptions for Context & Reasoning Module.

Defines a clean error hierarchy covering screen capture limits,
vision/OCR processing, and LLM client failures.
"""
from __future__ import annotations


class ContextReasoningError(Exception):
    """Base exception for all Context & Reasoning errors."""


class CaptureDisabledError(ContextReasoningError, PermissionError):
    """Raised when screen capture is attempted while capture is disabled (opt-in policy)."""


class SamplingRateLimitError(ContextReasoningError):
    """Raised when screen capture requests exceed configured sampling frequency (FPS)."""


class FrameSizeLimitError(ContextReasoningError, ValueError):
    """Raised when screen frame dimensions or byte size exceed configured limits."""


class VisionProcessingError(ContextReasoningError):
    """Raised when OCR or vision extraction encounters an unrecoverable failure."""


class LLMError(ContextReasoningError):
    """Base exception for LLM adapter errors."""


class LLMTimeoutError(LLMError, TimeoutError):
    """Raised when an LLM inference call exceeds the configured timeout."""


class LLMRetryExhaustedError(LLMError):
    """Raised when LLM invocation exhausts all retry attempts."""


class MalformedOutputError(LLMError, ValueError):
    """Raised when LLM response fails structured validation or contains malformed data."""
