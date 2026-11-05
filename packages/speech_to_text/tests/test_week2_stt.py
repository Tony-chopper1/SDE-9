"""
Comprehensive Contract & Unit Tests for Week 2 Speech-to-Text Deliverables.

Validates:
1. Audio preprocessing: 16 kHz resampling, stereo-to-mono downmix, amplitude normalization.
2. Error normalization: STTError envelopes, zero raw exception leaks.
3. Bounded retries: Exponential backoff, jitter, retry exhaustion.
4. Transcript reconciler: Monotonic ordering, duplicate suppression, interim-final reconciliation.
5. Orchestrator integration: End-to-end Chunk -> Provider -> Transcript events pipeline in mock mode.
"""

from __future__ import annotations

import math
import struct
import time
import pytest

from packages.audio import AudioConfig, MockMicrophoneSource
from packages.speech_to_text.exceptions import (
    STTConnectionError,
    STTError,
    STTProviderError,
    STTTimeoutError,
    normalize_stt_exception,
)
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.models import TranscriptEvent, TranscriptSegment
from packages.speech_to_text.orchestrator import OrchestratorState, SpeechToTextOrchestrator
from packages.speech_to_text.preprocessor import (
    AudioPreprocessError,
    AudioPreprocessor,
)
from packages.speech_to_text.reconciler import TranscriptReconciler
from packages.speech_to_text.retry import BoundedRetryHandler


# ===========================================================================
# 1. Audio Preprocessor Tests
# ===========================================================================


class TestAudioPreprocessor:
    """Tests for format validation, 16kHz resampling, downmix, and normalization."""

    def test_resample_upsample_8k_to_16k(self) -> None:
        proc = AudioPreprocessor()
        # 4 samples at 8kHz (0.5ms)
        raw_8k = struct.pack("<4h", 1000, 2000, 3000, 4000)
        resampled = proc.process(raw_8k, source_sample_rate=8000, channels=1)

        # Resampling 8kHz to 16kHz should double the sample count (8 samples = 16 bytes)
        assert len(resampled) == 16
        unpacked = struct.unpack("<8h", resampled)
        assert len(unpacked) == 8

    def test_resample_downsample_48k_to_16k(self) -> None:
        proc = AudioPreprocessor()
        # 12 samples at 48kHz (0.25ms)
        raw_48k = struct.pack("<12h", *([1500] * 12))
        resampled = proc.process(raw_48k, source_sample_rate=48000, channels=1)

        # 48kHz -> 16kHz is 1/3 ratio: 12 samples -> 4 samples = 8 bytes
        assert len(resampled) == 8

    def test_stereo_to_mono_downmixing(self) -> None:
        proc = AudioPreprocessor(enable_normalization=False)
        # 2 stereo frames: (L=1000, R=2000), (L=3000, R=4000) -> 8 bytes
        raw_stereo = struct.pack("<4h", 1000, 2000, 3000, 4000)
        mono = proc.process(raw_stereo, source_sample_rate=16000, channels=2)

        # Mono should be 2 samples (4 bytes): (1000+2000)//2 = 1500, (3000+4000)//2 = 3500
        assert len(mono) == 4
        unpacked = struct.unpack("<2h", mono)
        assert unpacked == (1500, 3500)

    def test_misaligned_bytes_raises_preprocess_error(self) -> None:
        proc = AudioPreprocessor()
        # 3 bytes is invalid for 16-bit PCM (needs multiple of 2)
        with pytest.raises(AudioPreprocessError) as exc:
            proc.process(b"\x00\x01\x02", source_sample_rate=16000, channels=1)
        assert "misaligned" in str(exc.value).lower()

    def test_amplitude_normalization_boosts_faint_audio(self) -> None:
        proc = AudioPreprocessor()
        # Faint signal peaking at 1000 (well below 32767)
        raw_faint = struct.pack("<4h", 200, -500, 1000, -800)
        normalized = proc.normalize_amplitude(raw_faint, target_peak_fraction=0.90)

        unpacked = struct.unpack("<4h", normalized)
        expected_peak = int(32767 * 0.90)
        assert max(abs(s) for s in unpacked) == expected_peak

    def test_amplitude_normalization_silence_handling(self) -> None:
        proc = AudioPreprocessor()
        silence = b"\x00" * 320
        assert proc.normalize_amplitude(silence) == silence

    def test_rms_db_calculation(self) -> None:
        proc = AudioPreprocessor()
        silence = b"\x00" * 320
        assert proc.calculate_rms_db(silence) == -100.0

        loud = struct.pack("<100h", *([16000] * 100))
        db = proc.calculate_rms_db(loud)
        assert -10.0 <= db <= -5.0


# ===========================================================================
# 2. Error Normalization & Hierarchy Tests
# ===========================================================================


class TestSTTExceptionsAndNormalization:
    """Verifies that all provider and external errors are normalized into typed STTErrors."""

    def test_timeout_normalization(self) -> None:
        raw_exc = TimeoutError("HTTP connection timed out")
        norm = normalize_stt_exception(raw_exc, provider_name="fake-stt")

        assert isinstance(norm, STTTimeoutError)
        assert norm.code == "STT_TIMEOUT"
        envelope = norm.to_envelope()
        assert envelope["code"] == "STT_TIMEOUT"
        assert "error" in envelope
        assert envelope["timestamp"] > 0

    def test_connection_error_normalization(self) -> None:
        raw_exc = ConnectionResetError("Remote server closed connection")
        norm = normalize_stt_exception(raw_exc, provider_name="fake-stt")

        assert isinstance(norm, STTConnectionError)
        assert norm.code == "STT_CONNECTION_ERROR"

    def test_arbitrary_provider_error_normalization(self) -> None:
        raw_exc = RuntimeError("Internal inference kernel crash")
        norm = normalize_stt_exception(raw_exc, provider_name="whisper-mock")

        assert isinstance(norm, STTProviderError)
        assert norm.code == "STT_PROVIDER_ERROR"
        assert norm.details["provider"] == "whisper-mock"
        assert norm.details["original_error_type"] == "RuntimeError"

    def test_stt_error_preserves_itself(self) -> None:
        original = STTTimeoutError("Already normalized", timeout_seconds=5.0)
        assert normalize_stt_exception(original) is original


# ===========================================================================
# 3. Bounded Retry Handler Tests
# ===========================================================================


class TestBoundedRetryHandler:
    """Tests exponential backoff, jitter, and retry exhaustion."""

    def test_successful_execution_without_retries(self) -> None:
        handler = BoundedRetryHandler(max_retries=3)
        result = handler.execute(lambda x: x * 2, 21)
        assert result == 42

    def test_transient_failure_succeeds_on_retry(self) -> None:
        attempts = 0

        def flaky_service() -> str:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("Temporary glitch")
            return "recovered"

        handler = BoundedRetryHandler(max_retries=3, base_backoff_sec=0.005)
        res = handler.execute(flaky_service)
        assert res == "recovered"
        assert attempts == 3

    def test_retry_exhaustion_raises_normalized_error(self) -> None:
        attempts = 0

        def always_fails() -> None:
            nonlocal attempts
            attempts += 1
            raise TimeoutError("Persistent provider outage")

        handler = BoundedRetryHandler(max_retries=2, base_backoff_sec=0.005)
        with pytest.raises(STTTimeoutError) as exc_info:
            handler.execute(always_fails)

        assert exc_info.value.code == "STT_TIMEOUT"
        assert exc_info.value.details["total_attempts"] == 3  # initial + 2 retries

    def test_non_retriable_error_fails_immediately(self) -> None:
        attempts = 0

        def bad_params() -> None:
            nonlocal attempts
            attempts += 1
            raise ValueError("Corrupt audio headers")

        handler = BoundedRetryHandler(max_retries=3, base_backoff_sec=0.005)
        with pytest.raises(STTError):
            handler.execute(bad_params)

        assert attempts == 1  # No retries on non-retriable error


# ===========================================================================
# 4. Transcript Reconciler Tests
# ===========================================================================


class TestTranscriptReconciler:
    """Tests chronological ordering, duplicate suppression, and interim-final reconciliation."""

    def test_monotonic_chronological_ordering(self) -> None:
        rec = TranscriptReconciler(session_id="order-test")

        # Ingest out of order: S2, then S1, then S3
        s2 = TranscriptSegment(id="s2", text="world", start_time=1.0, end_time=1.5, is_final=True)
        s1 = TranscriptSegment(id="s1", text="Hello", start_time=0.0, end_time=0.9, is_final=True)
        s3 = TranscriptSegment(id="s3", text="again", start_time=1.6, end_time=2.0, is_final=True)

        rec.process_segment(s2)
        rec.process_segment(s1)
        rec.process_segment(s3)

        ordered = rec.finalized_segments
        assert [s.id for s in ordered] == ["s1", "s2", "s3"]
        assert rec.get_finalized_text() == "Hello world again"

    def test_duplicate_segment_suppression(self) -> None:
        rec = TranscriptReconciler()
        seg = TranscriptSegment(id="s1", text="Duplicate test", start_time=0.0, end_time=1.0, is_final=True)

        ev1 = rec.process_segment(seg)
        assert ev1 is not None

        # Re-send exact same segment
        ev2 = rec.process_segment(seg)
        assert ev2 is None
        assert rec.duplicate_count == 1

        # Re-send identical text and timestamps with different ID
        seg_same_content = TranscriptSegment(id="s1-dup", text="Duplicate test", start_time=0.0, end_time=1.0, is_final=True)
        ev3 = rec.process_segment(seg_same_content)
        assert ev3 is None
        assert rec.duplicate_count == 2

    def test_interim_evolution_and_final_reconciliation(self) -> None:
        rec = TranscriptReconciler()

        # Step 1: Interim draft
        p1 = TranscriptSegment(id="p1", text="Why is", start_time=0.0, end_time=0.5, is_final=False)
        ev1 = rec.process_segment(p1)
        assert ev1.event_type == "transcript.interim"
        assert rec.get_full_transcript() == "Why is"
        assert rec.get_finalized_text() == ""

        # Step 2: Interim extends
        p2 = TranscriptSegment(id="p2", text="Why is this application", start_time=0.0, end_time=1.0, is_final=False)
        ev2 = rec.process_segment(p2)
        assert ev2.event_type == "transcript.interim"
        assert rec.get_full_transcript() == "Why is this application"

        # Step 3: Final commitment arrives
        f1 = TranscriptSegment(id="f1", text="Why is this application showing an error?", start_time=0.0, end_time=1.5, is_final=True)
        ev3 = rec.process_segment(f1)
        assert ev3.event_type == "transcript.final"
        assert rec.active_interim is None
        assert rec.get_finalized_text() == "Why is this application showing an error?"

    def test_flush_promotes_interim_to_final(self) -> None:
        rec = TranscriptReconciler()
        interim = TranscriptSegment(id="draft-1", text="Testing flush", start_time=0.0, end_time=0.5, is_final=False)
        rec.process_segment(interim)

        assert rec.get_finalized_text() == ""
        flushed_event = rec.flush()
        assert flushed_event is not None
        assert flushed_event.event_type == "transcript.final"
        assert rec.get_finalized_text() == "Testing flush"


# ===========================================================================
# 5. Full Orchestrator Integration Tests
# ===========================================================================


class TestSpeechToTextOrchestrator:
    """Verifies the complete Chunk -> Provider -> Transcript events pipeline in mock mode."""

    def test_end_to_end_orchestration_mock_mode(self) -> None:
        received_events: list[TranscriptEvent] = []
        orchestrator = SpeechToTextOrchestrator(
            session_id="sess-orch-001",
            on_event=lambda e: received_events.append(e),
        )
        orchestrator.start()
        assert orchestrator.state == OrchestratorState.RUNNING

        # Feed synthetic audio chunks (16kHz 16-bit mono = 32000 bytes/sec)
        # 4 frames of 960 bytes = 3840 bytes (exceeds min_chunk_bytes threshold of 3200)
        synthetic_frame = b"\x10\x00" * 480  # 960 bytes
        for i in range(4):
            orchestrator.push_audio(synthetic_frame, sample_rate=16000, channels=1, timestamp=float(i) * 0.03)

        assert orchestrator.total_frames_processed == 4
        assert len(received_events) >= 1
        assert any(e.event_type == "transcript.final" for e in received_events)

        utterance = orchestrator.stop()
        assert orchestrator.state == OrchestratorState.STOPPED
        assert utterance.is_complete is True
        assert len(utterance.full_text) > 0

    def test_orchestrator_handles_non_16k_input_with_resampling(self) -> None:
        orchestrator = SpeechToTextOrchestrator(session_id="resample-session")
        orchestrator.start()

        # Ingest 48 kHz frames; preprocessor should resample them cleanly to 16 kHz
        raw_48k = b"\x08\x00" * 1440  # 2880 bytes at 48kHz
        for _ in range(5):
            orchestrator.push_audio(raw_48k, sample_rate=48000, channels=1)

        orchestrator.flush()
        transcript = orchestrator.get_full_transcript()
        assert len(transcript) > 0

    def test_orchestrator_pause_and_resume_lifecycle(self) -> None:
        orchestrator = SpeechToTextOrchestrator()
        orchestrator.start()

        orchestrator.pause()
        assert orchestrator.state == OrchestratorState.PAUSED

        # Pushing audio while paused should be safely ignored
        ignored = orchestrator.push_audio(b"\x00" * 960)
        assert ignored == []

        orchestrator.resume()
        assert orchestrator.state == OrchestratorState.RUNNING

    def test_orchestrator_normalizes_provider_errors(self) -> None:
        class FailingTranscriber:
            def transcribe(self, audio_data: bytes, **kwargs):
                raise RuntimeError("Hardware ASIC engine offline")

        orchestrator = SpeechToTextOrchestrator(transcriber=FailingTranscriber())
        orchestrator.start()

        with pytest.raises(STTProviderError) as exc_info:
            orchestrator.push_audio(b"\x00" * 4000)

        assert exc_info.value.code == "STT_PROVIDER_ERROR"
        assert orchestrator.state == OrchestratorState.ERROR

    def test_synthetic_audio_fixture_pipeline(self) -> None:
        """Contract test using MockMicrophoneSource synthetic timeline fixture."""
        config = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=30)
        mic = MockMicrophoneSource(
            config=config,
            pattern="custom",
            custom_timeline=[("speech", 120), ("silence", 60), ("speech", 90)],
            max_frames=9,  # 270ms
        )

        orchestrator = SpeechToTextOrchestrator(session_id="fixture-test")
        orchestrator.start()

        with mic:
            for frame in mic.stream():
                # Ingest AudioFrame object directly
                orchestrator.push_audio(frame)

        utterance = orchestrator.stop()
        assert utterance.session_id == "fixture-test"
        assert utterance.is_complete is True
