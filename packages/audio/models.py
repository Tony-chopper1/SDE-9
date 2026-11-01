"""
Audio data models, schemas, and event envelopes for SDK-9.
Owner: Satwik A (feature/audio-vad)

Conforms to:
- docs/architecture.md (Audio component definitions)
- docs/integration-contracts.md (Event envelope & error envelope conventions)
- Provisional Speech-to-Text (STT) audio contract:
    * sample_rate: 16,000 Hz (mono, s16le PCM)
    * frame durations: 20 ms (640 bytes) and 30 ms (960 bytes)
    * explicit end-of-stream (None / StopIteration; empty frames rejected)
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from enum import Enum
import json
import math
import struct
import time
from typing import Any, Dict, List, Optional, Set
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.audio.exceptions import AudioConfigError, AudioFrameValidationError

SUPPORTED_SAMPLE_RATES: Set[int] = {8000, 16000, 22050, 24000, 32000, 44100, 48000}
SUPPORTED_BIT_DEPTHS: Set[int] = {16}
SUPPORTED_CHANNELS: Set[int] = {1, 2}
SUPPORTED_FRAME_DURATIONS_MS: Set[int] = {10, 20, 30}
SUPPORTED_FORMATS: Set[str] = {"s16le"}


class VADState(str, Enum):
    """Voice Activity Detection states."""
    SILENCE = "SILENCE"
    SPEECH_START = "SPEECH_START"
    SPEECH = "SPEECH"
    SPEECH_END = "SPEECH_END"


class AudioConfig(BaseModel):
    """Configuration schema for audio capture and streaming.

    Default is 16 kHz, 16-bit linear PCM (s16le), mono, 30ms frames (team default).
    Also supports 20ms frames matching provisional Speech-to-Text expectations.
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    sample_rate: int = Field(default=16000, description="Sampling rate in Hz (default: 16000)")
    bit_depth: int = Field(default=16, description="Bit depth per sample (default: 16)")
    channels: int = Field(default=1, description="Number of channels: 1=mono, 2=stereo (default: 1)")
    format: str = Field(default="s16le", description="Sample format string (default: 's16le')")
    frame_duration_ms: int = Field(default=30, description="Discrete frame duration in ms (20 or 30)")

    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v: int) -> int:
        if v not in SUPPORTED_SAMPLE_RATES:
            raise AudioConfigError(
                f"Unsupported sample rate: {v}. Supported rates: {sorted(SUPPORTED_SAMPLE_RATES)}",
                details={"sample_rate": v},
            )
        return v

    @field_validator("bit_depth")
    @classmethod
    def validate_bit_depth(cls, v: int) -> int:
        if v not in SUPPORTED_BIT_DEPTHS:
            raise AudioConfigError(
                f"Unsupported bit depth: {v}. Supported bit depths: {sorted(SUPPORTED_BIT_DEPTHS)}",
                details={"bit_depth": v},
            )
        return v

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: int) -> int:
        if v not in SUPPORTED_CHANNELS:
            raise AudioConfigError(
                f"Unsupported channel count: {v}. Supported channels: {sorted(SUPPORTED_CHANNELS)}",
                details={"channels": v},
            )
        return v

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in SUPPORTED_FORMATS:
            raise AudioConfigError(
                f"Unsupported audio format: '{v}'. Supported formats: {sorted(SUPPORTED_FORMATS)}",
                details={"format": v},
            )
        return v

    @field_validator("frame_duration_ms")
    @classmethod
    def validate_frame_duration(cls, v: int) -> int:
        if v not in SUPPORTED_FRAME_DURATIONS_MS:
            raise AudioConfigError(
                f"Unsupported frame duration: {v}ms. Supported durations: {sorted(SUPPORTED_FRAME_DURATIONS_MS)}ms",
                details={"frame_duration_ms": v},
            )
        return v

    @property
    def bytes_per_sample(self) -> int:
        """Number of bytes per single channel sample."""
        return self.bit_depth // 8

    @property
    def samples_per_frame(self) -> int:
        """Number of audio samples per frame across one channel."""
        return int(self.sample_rate * (self.frame_duration_ms / 1000.0))

    @property
    def frame_size_bytes(self) -> int:
        """Exact byte size of one PCM audio frame.
        - 16 kHz mono 20ms = 640 bytes (320 samples * 1 * 2)
        - 16 kHz mono 30ms = 960 bytes (480 samples * 1 * 2)
        """
        return self.samples_per_frame * self.channels * self.bytes_per_sample

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AudioConfig:
        """Instantiate AudioConfig from dictionary."""
        return cls.model_validate(data)


def _current_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_frame_id() -> str:
    return f"frame-{uuid.uuid4().hex[:10]}"


class AudioFrame(BaseModel):
    """Discrete audio frame supporting both existing team interfaces and provisional STT contracts.

    Time Fields Documentation:
        - timestamp: Unix epoch wall-clock timestamp in fractional seconds (e.g. 1730304000.123).
        - timestamp_ms: Audio-relative timeline position in milliseconds from stream start (e.g. 0.0, 20.0, 40.0).
        - timestamp_utc: ISO 8601 wall-clock UTC string (e.g. '2026-10-30T14:30:00.000000+00:00') for logging/auditability.
    """
    model_config = ConfigDict(extra="ignore")

    # Team interface fields
    data: bytes = Field(description="Raw 16-bit PCM byte payload (s16le)")
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix epoch wall-clock timestamp in fractional seconds",
    )
    sample_rate: int = Field(default=16000, description="Sampling frequency in Hz")
    frame_index: int = Field(default=0, description="Zero-based monotonic frame index")
    is_speech: bool = Field(default=False, description="Speech flag classification")

    # Provisional STT interface & metadata fields
    audio_data: Optional[bytes] = Field(default=None, description="Provisional STT payload alias")
    channels: int = Field(default=1, description="Number of audio channels (1=mono)")
    format: str = Field(default="s16le", description="Sample format string")
    frame_duration_ms: int = Field(default=30, description="Duration of this frame in ms (20 or 30)")
    sequence_number: int = Field(default=0, description="Monotonic sequence number")
    timestamp_ms: float = Field(default=0.0, description="Audio-relative stream offset in milliseconds")
    frame_id: str = Field(default_factory=_generate_frame_id, description="Unique frame identifier")
    timestamp_utc: str = Field(default_factory=_current_utc_iso, description="UTC ISO 8601 timestamp string")

    @model_validator(mode="before")
    @classmethod
    def align_and_validate_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Normalize data / audio_data
            raw_bytes = data.get("data")
            if raw_bytes is None:
                raw_bytes = data.get("audio_data")
            if raw_bytes is None:
                raise AudioFrameValidationError("audio_data/data must be provided as raw bytes")
            data["data"] = bytes(raw_bytes)
            data["audio_data"] = bytes(raw_bytes)

            # Sync frame_index / sequence_number if one is provided
            if "sequence_number" in data and "frame_index" not in data:
                data["frame_index"] = data["sequence_number"]
            elif "frame_index" in data and "sequence_number" not in data:
                data["sequence_number"] = data["frame_index"]

            # Calculate timestamp_ms if omitted but sequence_number and frame_duration_ms provided
            if "timestamp_ms" not in data:
                seq = data.get("sequence_number", data.get("frame_index", 0))
                dur = data.get("frame_duration_ms", 30)
                data["timestamp_ms"] = float(seq * dur)

        return data

    @model_validator(mode="after")
    def validate_frame(self) -> AudioFrame:
        # Guarantee audio_data is synchronized with data
        if self.audio_data != self.data:
            object.__setattr__(self, "audio_data", self.data)

        # Non-negative checks
        if self.sequence_number < 0 or self.frame_index < 0:
            raise AudioFrameValidationError(
                f"sequence_number and frame_index must be non-negative, got seq={self.sequence_number}, idx={self.frame_index}",
                details={"sequence_number": self.sequence_number, "frame_index": self.frame_index},
            )
        if self.timestamp_ms < 0.0:
            raise AudioFrameValidationError(
                f"timestamp_ms must be non-negative, got {self.timestamp_ms}",
                details={"timestamp_ms": self.timestamp_ms},
            )
        if self.format not in SUPPORTED_FORMATS:
            raise AudioFrameValidationError(
                f"Unsupported frame format: '{self.format}'. Expected: {sorted(SUPPORTED_FORMATS)}"
            )

        # Expected size calculation:
        samples_per_frame = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        expected_size = samples_per_frame * self.channels * 2  # 2 bytes per sample for s16le
        actual_size = len(self.data)

        if actual_size != expected_size:
            if actual_size == 0:
                raise AudioFrameValidationError(
                    "Empty audio frame rejected. End-of-stream must be signaled via EOF (None) or explicit event, not an empty frame.",
                    details={"frame_id": self.frame_id, "actual_bytes": 0, "expected_bytes": expected_size},
                )
            raise AudioFrameValidationError(
                f"Audio frame byte length mismatch: expected {expected_size} bytes ({self.frame_duration_ms}ms at {self.sample_rate}Hz), got {actual_size} bytes",
                details={
                    "expected_bytes": expected_size,
                    "actual_bytes": actual_size,
                    "frame_id": self.frame_id,
                },
            )

        return self

    @property
    def duration_ms(self) -> float:
        """Duration of this frame in milliseconds."""
        return float(self.frame_duration_ms)

    @property
    def config(self) -> AudioConfig:
        """Derived AudioConfig representing frame configuration."""
        return AudioConfig(
            sample_rate=self.sample_rate,
            channels=self.channels,
            bit_depth=16,
            format=self.format,
            frame_duration_ms=self.frame_duration_ms,
        )

    def calculate_rms(self) -> float:
        """Compute the Root Mean Square (RMS) amplitude of 16-bit PCM samples.
        Returns a value between 0.0 and 32768.0.
        """
        if not self.data:
            return 0.0
        sample_count = len(self.data) // 2
        if sample_count == 0:
            return 0.0
        samples = struct.unpack(f"<{sample_count}h", self.data)
        sum_squares = sum(s * s for s in samples)
        return math.sqrt(sum_squares / sample_count)

    def calculate_dbfs(self) -> float:
        """Compute decibels relative to full scale (dBFS).
        Full-scale 16-bit sine wave peaks at 0 dBFS. Silence returns -100.0 dBFS.
        """
        rms = self.calculate_rms()
        if rms <= 1e-4:
            return -100.0
        db = 20.0 * math.log10(rms / 32767.0)
        return max(db, -100.0)

    def to_dict(self, include_raw_bytes: bool = False) -> Dict[str, Any]:
        """Serialize frame metadata to dictionary. Excludes raw bytes by default."""
        res: Dict[str, Any] = {
            "frame_id": self.frame_id,
            "frame_index": self.frame_index,
            "sequence_number": self.sequence_number,
            "timestamp": self.timestamp,
            "timestamp_ms": round(self.timestamp_ms, 2),
            "timestamp_utc": self.timestamp_utc,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format,
            "frame_duration_ms": self.frame_duration_ms,
            "byte_length": len(self.data),
            "is_speech": self.is_speech,
            "rms": round(self.calculate_rms(), 2),
            "dbfs": round(self.calculate_dbfs(), 2),
        }
        if include_raw_bytes:
            res["audio_data_base64"] = base64.b64encode(self.data).decode("ascii")
        return res


class VADResult(BaseModel):
    """Voice Activity Detection classification result for an individual frame."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    is_speech: bool = Field(description="True if speech is detected, False for silence")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Confidence score [0.0, 1.0]")
    energy_db: float = Field(default=-100.0, description="Measured frame energy in dBFS")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic engine metadata")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize VAD result."""
        return self.model_dump()


class VADEvent(BaseModel):
    """Internal Voice Activity Detection event representing state transitions or frame classifications.

    Preserves existing team interface (state, timestamp, energy_level, confidence).
    Can be projected into the shared SDK-9 EventEnvelope via to_envelope().
    """
    model_config = ConfigDict(frozen=True, extra="ignore")

    state: VADState = Field(description="VAD state (SILENCE, SPEECH_START, SPEECH, SPEECH_END)")
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix epoch wall-clock timestamp in fractional seconds",
    )
    energy_level: float = Field(description="Calculated frame energy level (e.g. RMS or dBFS)")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Classification confidence [0.0, 1.0]")
    frame_index: int = Field(default=0, description="Associated audio frame index")
    timestamp_ms: Optional[float] = Field(default=None, description="Audio-relative stream offset in ms")

    def to_envelope(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        producer: str = "packages.audio",
    ) -> EventEnvelope:
        """Project this internal VADEvent into the shared SDK-9 EventEnvelope."""
        resolved_type = event_type or f"audio.vad.{self.state.value.lower()}"
        return EventEnvelope.create(
            event_type=resolved_type,
            session_id=session_id,
            correlation_id=correlation_id,
            producer=producer,
            payload={
                "state": self.state.value,
                "energy_level": self.energy_level,
                "confidence": self.confidence,
                "frame_index": self.frame_index,
                "timestamp_ms": self.timestamp_ms,
                "timestamp_epoch": self.timestamp,
            },
        )


class EventEnvelope(BaseModel):
    """Shared SDK-9 Event Envelope strictly conforming to docs/integration-contracts.md."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    event_id: str = Field(description="Unique event UUID (e.g. 'evt-12345')")
    event_type: str = Field(description="Dot-notated event name (e.g. 'audio.vad.speech_start')")
    schema_version: str = Field(default="1.0.0", description="Schema version of this event")
    session_id: str = Field(description="Session identifier")
    correlation_id: str = Field(description="Tracing correlation identifier")
    timestamp: str = Field(description="UTC ISO 8601 wall-clock timestamp string")
    producer: str = Field(default="packages.audio", description="Module producing the event")
    payload: Dict[str, Any] = Field(description="Module-specific event payload dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize envelope to dictionary."""
        return self.model_dump()

    def to_json(self) -> str:
        """Serialize envelope to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def create(
        cls,
        event_type: str,
        session_id: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        producer: str = "packages.audio",
        schema_version: str = "1.0.0",
    ) -> EventEnvelope:
        """Convenience factory creating a fully compliant SDK-9 EventEnvelope."""
        now_utc = datetime.now(timezone.utc).isoformat()
        evt_id = f"evt-{uuid.uuid4().hex[:12]}"
        corr_id = correlation_id or f"corr-{uuid.uuid4().hex[:8]}"
        return cls(
            event_id=evt_id,
            event_type=event_type,
            schema_version=schema_version,
            session_id=session_id,
            correlation_id=corr_id,
            timestamp=now_utc,
            producer=producer,
            payload=payload,
        )
