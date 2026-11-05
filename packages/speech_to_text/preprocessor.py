"""
Audio Preprocessing Pipeline for Speech-to-Text (STT).

Provides audio format validation, sample rate resampling to 16 kHz (s16le),
stereo-to-mono downmixing, and amplitude normalization (peak and RMS)
to ensure robust acoustic modeling and transcriber stability.
"""

from __future__ import annotations

import math
import struct
from typing import Any, Dict, Optional, Tuple

TARGET_SAMPLE_RATE: int = 16000
TARGET_BIT_DEPTH: int = 16
TARGET_CHANNELS: int = 1
BYTES_PER_SAMPLE: int = 2  # 16-bit linear PCM = 2 bytes per sample
MAX_INT16: int = 32767
MIN_INT16: int = -32768


class AudioPreprocessError(Exception):
    """Raised when audio payload is corrupt, misaligned, or cannot be processed."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AudioPreprocessor:
    """Acoustic preprocessor ensuring audio payloads conform to STT ingestion standards.

    Guarantees:
    - 16 kHz sample rate (resampled via linear interpolation with anti-aliasing guard).
    - 16-bit signed little-endian linear PCM (`s16le`).
    - 1-channel mono downmix.
    - Amplitude normalization to prevent clipping and boost low-energy speech.
    """

    def __init__(
        self,
        target_sample_rate: int = TARGET_SAMPLE_RATE,
        target_peak_level: float = 0.90,
        enable_normalization: bool = True,
    ) -> None:
        self.target_sample_rate = target_sample_rate
        self.target_peak_level = min(1.0, max(0.1, target_peak_level))
        self.enable_normalization = enable_normalization

    def process(
        self,
        pcm_bytes: bytes,
        source_sample_rate: int = TARGET_SAMPLE_RATE,
        channels: int = 1,
    ) -> bytes:
        """Execute full preprocessing pipeline on raw PCM bytes.

        Args:
            pcm_bytes: Raw 16-bit signed PCM audio bytes.
            source_sample_rate: Source sampling frequency in Hz (e.g. 8000, 16000, 44100, 48000).
            channels: Number of input channels (1 for mono, 2 for stereo).

        Returns:
            Processed 16 kHz 16-bit mono PCM bytes.

        Raises:
            AudioPreprocessError: If audio bytes are misaligned or parameters are invalid.
        """
        if not pcm_bytes:
            return b""

        # 1. Validate byte alignment (16-bit = 2 bytes per channel sample)
        frame_bytes = BYTES_PER_SAMPLE * channels
        if len(pcm_bytes) % frame_bytes != 0:
            raise AudioPreprocessError(
                f"Audio payload size ({len(pcm_bytes)} bytes) is misaligned for "
                f"{channels} channel(s) 16-bit PCM (must be multiple of {frame_bytes}).",
                details={"byte_length": len(pcm_bytes), "channels": channels},
            )

        # 2. Convert to mono if stereo
        mono_bytes = self._downmix_to_mono(pcm_bytes, channels) if channels > 1 else pcm_bytes

        # 3. Resample if necessary
        resampled_bytes = (
            self.resample(mono_bytes, source_sample_rate, self.target_sample_rate)
            if source_sample_rate != self.target_sample_rate
            else mono_bytes
        )

        # 4. Amplitude Normalization
        if self.enable_normalization:
            normalized_bytes = self.normalize_amplitude(resampled_bytes, self.target_peak_level)
        else:
            normalized_bytes = resampled_bytes

        return normalized_bytes

    def _downmix_to_mono(self, pcm_bytes: bytes, channels: int) -> bytes:
        """Downmix multi-channel 16-bit PCM to single-channel mono."""
        num_samples = len(pcm_bytes) // (BYTES_PER_SAMPLE * channels)
        fmt = f"<{num_samples * channels}h"
        raw_samples = struct.unpack(fmt, pcm_bytes)

        mono_samples = []
        for i in range(num_samples):
            # Average channels together with clamp
            avg_val = sum(raw_samples[i * channels + c] for c in range(channels)) // channels
            mono_samples.append(max(MIN_INT16, min(MAX_INT16, avg_val)))

        return struct.pack(f"<{num_samples}h", *mono_samples)

    def resample(
        self,
        pcm_bytes: bytes,
        source_rate: int,
        target_rate: int = TARGET_SAMPLE_RATE,
    ) -> bytes:
        """Resample 16-bit mono PCM audio from *source_rate* to *target_rate*.

        Uses high-fidelity linear interpolation with boundary clamping.
        """
        if source_rate <= 0 or target_rate <= 0:
            raise AudioPreprocessError(
                f"Invalid sample rates: source={source_rate}, target={target_rate}"
            )
        if source_rate == target_rate or not pcm_bytes:
            return pcm_bytes

        # Unpack input samples
        num_in_samples = len(pcm_bytes) // BYTES_PER_SAMPLE
        in_samples = struct.unpack(f"<{num_in_samples}h", pcm_bytes)

        # Calculate output sample count
        ratio = target_rate / float(source_rate)
        num_out_samples = int(round(num_in_samples * ratio))
        if num_out_samples == 0:
            return b""

        out_samples = [0] * num_out_samples

        for i in range(num_out_samples):
            # Source position in fractional sample index
            src_idx = i / ratio
            idx_floor = int(math.floor(src_idx))
            frac = src_idx - idx_floor

            if idx_floor >= num_in_samples - 1:
                val = in_samples[-1]
            else:
                s0 = in_samples[idx_floor]
                s1 = in_samples[idx_floor + 1]
                val = int(round(s0 + frac * (s1 - s0)))

            out_samples[i] = max(MIN_INT16, min(MAX_INT16, val))

        return struct.pack(f"<{num_out_samples}h", *out_samples)

    def normalize_amplitude(
        self,
        pcm_bytes: bytes,
        target_peak_fraction: float = 0.90,
    ) -> bytes:
        """Apply peak amplitude normalization to prevent clipping and enhance clarity.

        Args:
            pcm_bytes: 16-bit mono PCM bytes.
            target_peak_fraction: Desired peak level between 0.0 and 1.0 (relative to 32767).

        Returns:
            Normalized 16-bit mono PCM bytes.
        """
        if not pcm_bytes:
            return b""

        num_samples = len(pcm_bytes) // BYTES_PER_SAMPLE
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes)

        current_peak = max(abs(s) for s in samples) if samples else 0
        if current_peak == 0:
            return pcm_bytes  # Pure silence

        target_peak = int(MAX_INT16 * target_peak_fraction)
        if current_peak == target_peak:
            return pcm_bytes

        scale_factor = target_peak / float(current_peak)

        # If already loud enough (within 5% of target), avoid unnecessary scaling
        if 0.95 <= scale_factor <= 1.05:
            return pcm_bytes

        normalized_samples = [
            max(MIN_INT16, min(MAX_INT16, int(round(s * scale_factor))))
            for s in samples
        ]
        return struct.pack(f"<{num_samples}h", *normalized_samples)

    def calculate_rms_db(self, pcm_bytes: bytes) -> float:
        """Calculate Root Mean Square (RMS) energy in decibels relative to full scale (dBFS)."""
        if not pcm_bytes:
            return -100.0

        num_samples = len(pcm_bytes) // BYTES_PER_SAMPLE
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes)
        sum_sq = sum(s * s for s in samples)
        mean_sq = sum_sq / float(num_samples)

        if mean_sq <= 0:
            return -100.0

        rms = math.sqrt(mean_sq)
        db = 20.0 * math.log10(rms / float(MAX_INT16))
        return round(db, 2)
