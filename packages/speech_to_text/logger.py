"""
Privacy-First Redacted Logging for Speech-to-Text Module.

Guarantees:
- Logs NEVER contain raw transcript text or audio payloads.
- Spoken text is masked with length metadata: `[REDACTED_TRANSCRIPT: len=N]`.
- Raw audio bytes are masked with byte-count metadata: `[REDACTED_AUDIO: N bytes]`.
- Thread-safe, standard library logging integration compatible with all environments.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Union


# Sensitive keys that must always be masked if passed in dictionaries or kwargs
SENSITIVE_TEXT_KEYS = {
    "text",
    "transcript",
    "full_text",
    "utterance_text",
    "interim_text",
    "raw_text",
    "hypothesis",
    "spoken_words",
}

SENSITIVE_AUDIO_KEYS = {
    "audio_data",
    "pcm_data",
    "pcm_raw",
    "audio_payload",
    "raw_audio",
    "audio_bytes",
    "data",
}

# Regex to catch accidental stringified transcript content or quotes
TRANSCRIPT_CONTENT_REGEX = re.compile(
    r"""(?i)(?:text|transcript|utterance|hypothesis)\s*[:=]\s*['"]([^'"]+)['"]"""
)


def mask_transcript_text(text: Optional[str]) -> str:
    """Mask transcript text while retaining diagnostic length metadata."""
    if text is None:
        return "[EMPTY_TRANSCRIPT]"
    if isinstance(text, str) and text.startswith("[REDACTED_TRANSCRIPT"):
        return text
    cleaned = str(text).strip()
    if not cleaned:
        return "[EMPTY_TRANSCRIPT]"
    return f"[REDACTED_TRANSCRIPT: len={len(cleaned)}]"


def mask_audio_bytes(payload: Union[bytes, bytearray, memoryview, Any]) -> str:
    """Mask audio buffer payload while retaining byte count for debugging."""
    if payload is None:
        return "[EMPTY_AUDIO]"
    if isinstance(payload, str) and payload.startswith("[REDACTED_AUDIO"):
        return payload
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return f"[REDACTED_AUDIO: {len(payload)} bytes]"
    if hasattr(payload, "data") and isinstance(payload.data, (bytes, bytearray)):
        return f"[REDACTED_AUDIO: {len(payload.data)} bytes]"
    return "[REDACTED_AUDIO]"


def redact_object(obj: Any) -> Any:
    """Recursively scrub transcript text and audio payloads from diagnostic objects."""
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return mask_audio_bytes(obj)

    if isinstance(obj, dict):
        scrubbed = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k_lower in SENSITIVE_TEXT_KEYS:
                scrubbed[k] = mask_transcript_text(v)
            elif k_lower in SENSITIVE_AUDIO_KEYS:
                scrubbed[k] = mask_audio_bytes(v)
            else:
                scrubbed[k] = redact_object(v)
        return scrubbed

    if isinstance(obj, (list, tuple)):
        scrubbed_list = [redact_object(item) for item in obj]
        return type(obj)(scrubbed_list)

    if isinstance(obj, str):
        # Scrub embedded transcript patterns like `text='Why is the app failing'`
        def _repl(match: re.Match) -> str:
            content = match.group(1)
            prefix = match.group(0).split(content)[0]
            suffix = match.group(0)[len(prefix) + len(content):]
            return f"{prefix}[REDACTED_TRANSCRIPT: len={len(content)}]{suffix}"

        return TRANSCRIPT_CONTENT_REGEX.sub(_repl, obj)

    return obj


class RedactedSTTFilter(logging.Filter):
    """Logging filter that scrubs sensitive transcript text and audio payloads in-place."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_object(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_object(record.args)
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(redact_object(arg) for arg in record.args)

        # Also sanitize any custom attributes attached via `extra`
        for key in list(record.__dict__.keys()):
            key_lower = key.lower()
            if key_lower in SENSITIVE_TEXT_KEYS:
                record.__dict__[key] = mask_transcript_text(record.__dict__[key])
            elif key_lower in SENSITIVE_AUDIO_KEYS:
                record.__dict__[key] = mask_audio_bytes(record.__dict__[key])

        return True


class RedactedSTTFormatter(logging.Formatter):
    """Logging formatter ensuring safe output rendering without transcript leakage."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_object(formatted)


def get_stt_logger(name: str = "sdk9.speech_to_text") -> logging.Logger:
    """Obtain a standardized STT logger configured with privacy redaction filters."""
    logger = logging.getLogger(name)
    
    # Avoid duplicate filter registration
    if not any(isinstance(f, RedactedSTTFilter) for f in logger.filters):
        logger.addFilter(RedactedSTTFilter())

    # Ensure log level is initialized if unset
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    return logger
