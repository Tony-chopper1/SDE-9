"""
Privacy Redaction, Benchmark Validation, and CI Regression Tests for Speech-to-Text.
Owner: Pavan (feature/pavan-week4) - Days 22-29

Acceptance Criteria Validated:
1. Logs never contain transcript text or audio payloads, and a test asserts the redaction.
2. The latency benchmark runs on approved synthetic fixtures (mock provider by default), and its results are recorded.
3. The regression fixtures run in CI.
"""

from __future__ import annotations

import io
import logging
import pytest

from packages.speech_to_text.benchmark import run_latency_benchmark
from packages.speech_to_text.fixtures import SyntheticAudioFixtures
from packages.speech_to_text.logger import (
    RedactedSTTFilter,
    RedactedSTTFormatter,
    get_stt_logger,
    mask_audio_bytes,
    mask_transcript_text,
    redact_object,
)
from packages.speech_to_text.orchestrator import OrchestratorState, SpeechToTextOrchestrator
from packages.speech_to_text.preprocessor import AudioPreprocessor


class TestWeek4PrivacyRedactedLogging:
    """Validates that logs strictly omit raw spoken transcripts and binary audio buffers."""

    def test_logs_never_contain_transcript_text_or_audio_payloads(self):
        """Acceptance Criteria: Logs never contain transcript text or audio payloads, and a test asserts the redaction."""
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(RedactedSTTFormatter("%(levelname)s:%(name)s:%(message)s"))
        handler.addFilter(RedactedSTTFilter())

        logger = get_stt_logger("test.privacy.logger")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False

        # Attempt to log confidential user transcript and raw PCM audio
        secret_user_speech = "My secret banking PIN is 4829 and SSN is 000-11-2222"
        confidential_audio_bytes = b"\xde\xad\xbe\xef" * 800  # 3200 bytes

        # 1. Log with string message
        logger.info(f"Received speech input: text='{secret_user_speech}'")

        # 2. Log with extra dictionary and session identifier
        logger.info(
            "Transcriber committed chunk for session %s",
            "sess-xyz",
            extra={
                "transcript": secret_user_speech,
                "audio_payload": confidential_audio_bytes,
                "session_id": "sess-xyz",
            },
        )

        # 3. Log with structured formatting args
        logger.warning(
            "Reconciliation warning for payload: %s",
            {"text": secret_user_speech, "raw_audio": confidential_audio_bytes},
        )

        handler.flush()
        captured_logs = log_stream.getvalue()

        # Strict Assertions: Original text and bytes must NEVER appear in logs
        assert secret_user_speech not in captured_logs, "LEAK: Raw transcript text was found in log output!"
        assert "4829" not in captured_logs, "LEAK: Sensitive numbers leaked into logs!"
        assert "\\xde\\xad" not in captured_logs, "LEAK: Raw audio bytes leaked into logs!"

        # Assert Redacted Masks ARE present
        assert "[REDACTED_TRANSCRIPT: len=" in captured_logs
        assert "[REDACTED_AUDIO: 3200 bytes]" in captured_logs
        assert "sess-xyz" in captured_logs  # Non-sensitive diagnostic metadata is preserved

    def test_redact_object_recursive_sanitization(self):
        """Verify deep dictionaries and nested lists are scrubbed thoroughly."""
        sensitive_payload = {
            "session_id": "safe-session-123",
            "metadata": {
                "spoken_words": "Schedule an urgent doctor appointment",
                "nested_audio": {
                    "pcm_raw": b"\x01\x02\x03\x04" * 100,
                },
            },
            "unrelated_key": 42,
        }
        scrubbed = redact_object(sensitive_payload)

        assert scrubbed["session_id"] == "safe-session-123"
        assert scrubbed["unrelated_key"] == 42
        assert scrubbed["metadata"]["spoken_words"] == "[REDACTED_TRANSCRIPT: len=37]"
        assert scrubbed["metadata"]["nested_audio"]["pcm_raw"] == "[REDACTED_AUDIO: 400 bytes]"


class TestWeek4LatencyBenchmarkAndRegressionFixtures:
    """Validates latency benchmarking and synthetic CI regression fixtures."""

    def test_latency_benchmark_runs_and_passes_sla_in_mock_mode(self):
        """Acceptance Criteria: The latency benchmark runs on approved synthetic fixtures and passes SLA."""
        report = run_latency_benchmark(iterations=50, warmups=5, max_acceptable_e2e_p95_ms=50.0)

        assert report.iterations == 50
        assert report.sla_passed is True
        # Verify p95 end-to-end latency is sub-millisecond on mock provider (< 50ms SLA)
        assert report.end_to_end_frame_latency.p95_ms < 50.0
        assert report.preprocessing_latency.mean_ms < 10.0
        assert report.transcription_latency.mean_ms < 10.0

    def test_regression_fixtures_multi_sample_rate_resampling(self):
        """Acceptance Criteria: The regression fixtures run in CI (multi-rate resampling)."""
        preprocessor = AudioPreprocessor()
        fixtures = SyntheticAudioFixtures.multi_sample_rate_fixtures()

        for sr, ch, data in fixtures:
            processed = preprocessor.process(data, source_sample_rate=sr, channels=ch)
            assert len(processed) > 0
            # Target is always 16kHz s16le mono (2 bytes per sample)
            assert len(processed) % 2 == 0

    def test_regression_fixtures_out_of_order_stream(self):
        """Acceptance Criteria: The regression fixtures run in CI (out-of-order packet simulation)."""
        orchestrator = SpeechToTextOrchestrator(session_id="ci-ooo-test")
        orchestrator.start()

        disordered_frames = SyntheticAudioFixtures.out_of_order_stream(total_frames=10)
        for frame in disordered_frames:
            orchestrator.push_audio(frame.data, sequence_number=frame.sequence_number)

        # Disordered frames were registered
        assert orchestrator.out_of_order_chunks_count > 0
        assert orchestrator.state == OrchestratorState.RUNNING

    def test_regression_fixtures_sequence_gaps(self):
        """Acceptance Criteria: The regression fixtures run in CI (sequence gap loss simulation)."""
        orchestrator = SpeechToTextOrchestrator(session_id="ci-gaps-test")
        orchestrator.start()

        gap_frames = SyntheticAudioFixtures.sequence_gap_stream()
        for frame in gap_frames:
            orchestrator.push_audio(frame.data, sequence_number=frame.sequence_number)

        # Sequence gap was tracked
        assert orchestrator.missing_chunks_count > 0
        assert orchestrator.state == OrchestratorState.RUNNING
