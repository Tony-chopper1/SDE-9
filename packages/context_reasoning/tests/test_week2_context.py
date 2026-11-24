"""
Comprehensive Unit and Integration Tests for SDK-9 Week 2 Context & Reasoning.

Validates:
1. Opt-in screen capture adapter with sampling and size limits.
2. OCR and vision adapter interface and deterministic mock.
3. Bounded context builder with recency, relevance, token budgeting, and stale filtering.
4. LLM client adapter with timeout, retry, structured output validation, and malformed-output recovery.
"""
from __future__ import annotations

import json
import time
import pytest
from pydantic import BaseModel, ValidationError

from packages.context_reasoning.capture_adapter import CaptureAdapter
from packages.context_reasoning.vision_adapter import BaseVisionAdapter, MockVisionAdapter
from packages.context_reasoning.context_builder import ContextBuilder, approximate_tokens
from packages.context_reasoning.llm_adapter import (
    BaseLLMClient,
    LLMAdapter,
    MockLLMClient,
)
from packages.context_reasoning.exceptions import (
    CaptureDisabledError,
    FrameSizeLimitError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    MalformedOutputError,
    SamplingRateLimitError,
    VisionProcessingError,
)
from packages.context_reasoning.models import (
    CaptureConfig,
    ContextBuilderConfig,
    ContextItem,
    ConversationContext,
    ConversationTurn,
    ReasoningRequest,
    ReasoningResult,
    ScreenContext,
    SourceReference,
    VisionRegion,
    VisionResult,
    WindowContext,
)


# =============================================================================
# 1. Capture Adapter Tests (Opt-in, Sampling, Size Limits)
# =============================================================================

class TestCaptureAdapter:
    """Tests for opt-in screen capture adapter and boundary enforcements."""

    def test_capture_off_by_default(self):
        """Verify screen capture is strictly disabled by default (privacy requirement)."""
        adapter = CaptureAdapter()
        assert adapter.is_enabled() is False
        assert adapter.config.capture_enabled is False

    def test_capture_disabled_raises_error(self):
        """Verify capture_frame raises CaptureDisabledError when disabled."""
        adapter = CaptureAdapter()
        with pytest.raises(CaptureDisabledError, match="disabled by default"):
            adapter.capture_frame()

    def test_enable_disable_lifecycle(self):
        """Verify enabling and disabling screen capture toggle."""
        adapter = CaptureAdapter()
        adapter.enable()
        assert adapter.is_enabled() is True

        frame = adapter.capture_frame(width=640, height=480)
        assert frame.is_synthetic is True
        assert frame.capture_enabled is True

        adapter.disable()
        assert adapter.is_enabled() is False
        with pytest.raises(CaptureDisabledError):
            adapter.capture_frame()

    def test_sampling_rate_limit_exceeded(self):
        """Verify SamplingRateLimitError is raised when capture frequency exceeds max_fps."""
        config = CaptureConfig(capture_enabled=True, max_fps=1.0)  # min 1.0s interval
        adapter = CaptureAdapter(config=config)

        # First capture succeeds
        adapter.capture_frame()

        # Immediate second capture should exceed rate limit
        with pytest.raises(SamplingRateLimitError, match="exceeded sampling limit"):
            adapter.capture_frame()

    def test_sampling_rate_limit_throttle_cached(self):
        """Verify throttle_cached=True returns the cached frame instead of error."""
        config = CaptureConfig(capture_enabled=True, max_fps=1.0)
        adapter = CaptureAdapter(config=config)

        frame1 = adapter.capture_frame()
        # Immediate second call with throttle_cached=True should return frame1
        frame2 = adapter.capture_frame(throttle_cached=True)
        assert frame1.frame_id == frame2.frame_id

    def test_dimension_overflow_downscale(self):
        """Verify dimensions exceeding limits are proportionally downscaled when downscale_on_overflow=True."""
        config = CaptureConfig(
            capture_enabled=True,
            max_width=1280,
            max_height=720,
            downscale_on_overflow=True,
        )
        adapter = CaptureAdapter(config=config)

        # Request 2560x1440 (2x size)
        frame = adapter.capture_frame(width=2560, height=1440)
        assert frame.width <= 1280
        assert frame.height <= 720
        assert frame.width == 1280
        assert frame.height == 720

    def test_dimension_overflow_raises_error(self):
        """Verify FrameSizeLimitError when downscale_on_overflow=False."""
        config = CaptureConfig(
            capture_enabled=True,
            max_width=1280,
            max_height=720,
            downscale_on_overflow=False,
        )
        adapter = CaptureAdapter(config=config)

        with pytest.raises(FrameSizeLimitError, match="exceed maximum allowed"):
            adapter.capture_frame(width=1920, height=1080)

    def test_byte_size_limit_exceeded(self):
        """Verify FrameSizeLimitError when payload exceeds max_bytes."""
        config = CaptureConfig(
            capture_enabled=True,
            max_bytes=1024,  # 1KB limit to trigger overflow on larger frames
        )
        adapter = CaptureAdapter(config=config)

        with pytest.raises(FrameSizeLimitError, match="exceeds maximum limit"):
            adapter.capture_frame(width=1920, height=1080)

    def test_telemetry_metrics_and_reset(self):
        """Verify capture counts and byte statistics in metrics."""
        adapter = CaptureAdapter(CaptureConfig(capture_enabled=True, max_fps=25.0))
        adapter.capture_frame(width=640, height=480)
        time.sleep(0.05)
        adapter.capture_frame(width=640, height=480)

        metrics = adapter.get_metrics()
        assert metrics["total_captures"] == 2
        assert metrics["total_bytes_captured"] > 0
        assert metrics["capture_enabled"] is True

        adapter.reset()
        assert adapter.get_metrics()["total_captures"] == 0


# =============================================================================
# 2. OCR and Vision Adapter Tests
# =============================================================================

class TestVisionAdapter:
    """Tests for OCR/Vision interface and MockVisionAdapter."""

    def test_vision_interface_contract(self):
        """Verify BaseVisionAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseVisionAdapter()  # abstract class

    def test_mock_vision_process_frame(self):
        """Verify MockVisionAdapter processes synthetic frames and outputs VisionResult."""
        adapter = MockVisionAdapter()
        frame = ScreenContext.create_synthetic(
            width=1280,
            height=720,
            visible_text="def test_ocr(): return 42",
        )

        result = adapter.process_frame(frame)
        assert isinstance(result, VisionResult)
        assert result.frame_id == frame.frame_id
        assert "def test_ocr(): return 42" in result.extracted_text
        assert result.confidence >= 0.90
        assert result.processing_time_ms > 0
        assert len(result.regions) == 3

    def test_mock_vision_region_segmentation(self):
        """Verify standard IDE regions (title bar, editor, terminal) are detected."""
        adapter = MockVisionAdapter()
        win = WindowContext(window_title="server.py - SDK-9")
        frame = ScreenContext.create_synthetic(
            width=1920,
            height=1080,
            active_window=win,
        )

        regions = adapter.detect_regions(frame)
        labels = [r.label for r in regions]
        assert "title_bar" in labels
        assert "code_editor" in labels
        assert "terminal_console" in labels

        title_region = next(r for r in regions if r.label == "title_bar")
        assert "server.py" in (title_region.text_content or "")

    def test_mock_vision_failure_mode(self):
        """Verify VisionProcessingError is raised when fail_mode is enabled."""
        adapter = MockVisionAdapter(fail_mode=True)
        frame = ScreenContext.create_synthetic()

        with pytest.raises(VisionProcessingError, match="Simulated vision hardware failure"):
            adapter.process_frame(frame)

        with pytest.raises(VisionProcessingError):
            adapter.extract_text(frame)


# =============================================================================
# 3. Bounded Context Builder Tests (Tokens, Stale, Relevance, Recency)
# =============================================================================

class TestContextBuilder:
    """Tests for Bounded Context Builder."""

    def test_approximate_tokens_utility(self):
        """Verify token estimation heuristic."""
        assert approximate_tokens("") == 0
        assert approximate_tokens("word") == 1
        # ~100 characters ≈ 25 tokens
        assert 20 <= approximate_tokens("a" * 100) <= 30

    def test_stale_filtering_context_items(self):
        """Verify items older than TTL are filtered out."""
        builder = ContextBuilder(ContextBuilderConfig(stale_threshold_seconds=10.0))
        now = time.time()

        fresh_item = ContextItem(content="fresh context", timestamp=now - 2.0)
        stale_item = ContextItem(content="stale context", timestamp=now - 15.0)

        filtered = builder.filter_stale_items([fresh_item, stale_item], now=now)
        assert len(filtered) == 1
        assert filtered[0].content == "fresh context"

    def test_is_screen_stale(self):
        """Verify screen frames older than screen_stale_seconds are flagged stale."""
        builder = ContextBuilder(ContextBuilderConfig(screen_stale_seconds=5.0))
        now = time.time()

        fresh_screen = ScreenContext(timestamp=now - 1.0)
        stale_screen = ScreenContext(timestamp=now - 10.0)

        assert builder.is_screen_stale(fresh_screen, now=now) is False
        assert builder.is_screen_stale(stale_screen, now=now) is True
        assert builder.is_screen_stale(None, now=now) is True

    def test_relevance_scoring(self):
        """Verify keyword matching scores overlap accurately."""
        builder = ContextBuilder()
        query = "find all audio test files"

        high_rel = "This module contains audio test files for mock mic."
        low_rel = "Unrelated database configuration for production users."

        score_high = builder.score_relevance(query, high_rel)
        score_low = builder.score_relevance(query, low_rel)

        assert score_high > score_low
        assert score_high >= 0.50

    def test_recency_scoring_decay(self):
        """Verify newer items receive higher recency scores."""
        builder = ContextBuilder()
        now = time.time()

        recent = builder.score_recency(now - 5.0, now=now)
        old = builder.score_recency(now - 300.0, now=now)

        assert recent > old
        assert recent > 0.80
        assert old < 0.30

    def test_token_budget_upper_bound_enforcement(self):
        """Verify assembled context never exceeds configured token_budget."""
        # Very small budget of 80 tokens
        config = ContextBuilderConfig(token_budget=80)
        builder = ContextBuilder(config=config)

        raw_context = ConversationContext(
            session_id="budget-session",
            active_window=WindowContext(visible_snippet="x = 1\n" * 500),  # large snippet
            history=[
                ConversationTurn(role="user", content="Turn " + str(i))
                for i in range(50)
            ],
            user_query="How to run tests?",
            context_items=[
                ContextItem(content="Item " + ("long text " * 30))
                for _ in range(10)
            ],
        )

        req = builder.build_context(raw_context)
        assert req.context is not None

        # Calculate total tokens across assembled request
        total_tokens = approximate_tokens(req.query)
        total_tokens += approximate_tokens(req.context.active_window.visible_snippet or "")
        for turn in req.context.history:
            total_tokens += approximate_tokens(f"{turn.role}: {turn.content}")
        for item in req.context_items:
            total_tokens += approximate_tokens(item.content)

        assert total_tokens <= config.token_budget

    def test_history_selection_prioritizes_recent_turns(self):
        """Verify sliding turn selection preserves chronological order while prioritizing recent turns."""
        builder = ContextBuilder(ContextBuilderConfig(token_budget=500))
        history = [
            ConversationTurn(role="user", content=f"Message {i}")
            for i in range(1, 11)
        ]

        # Allow 30 tokens for history
        selected, tokens = builder.select_history_turns(history, token_allowance=30)
        assert len(selected) > 0
        # The last message (Message 10) must be included
        assert any("Message 10" in t.content for t in selected)
        # Chronological order preserved
        assert selected[0].timestamp <= selected[-1].timestamp
        assert int(selected[0].content.split()[1]) < int(selected[-1].content.split()[1])


# =============================================================================
# 4. LLM Adapter Tests (Timeout, Retry, Structured Output Validation)
# =============================================================================

class TestLLMAdapter:
    """Tests for LLM Client Adapter."""

    def test_mock_llm_client_default(self):
        """Verify MockLLMClient produces valid JSON adhering to ReasoningResult."""
        client = MockLLMClient()
        output = client.complete("Search for *.py in directory")
        data = json.loads(output)

        assert data["intent"] == "FILE_SEARCH"
        assert data["requires_tool"] is True
        assert data["planned_tool_name"] == "file.search"

    def test_adapter_successful_invocation(self):
        """Verify LLMAdapter returns valid LLMResponse with structured Pydantic object."""
        adapter = LLMAdapter()
        response = adapter.invoke("Calculate 25 * 4")

        assert response.structured_data is not None
        assert isinstance(response.structured_data, ReasoningResult)
        assert response.structured_data.intent == "CALCULATE"
        assert response.structured_data.requires_tool is True
        assert response.retries_used == 0

    def test_adapter_retry_on_transient_failure(self):
        """Verify adapter recovers after transient upstream errors within max_retries."""
        # Fails 2 times, succeeds on 3rd attempt
        mock_client = MockLLMClient(fail_count=2)
        adapter = LLMAdapter(client=mock_client, max_retries=3, initial_delay_seconds=0.01)

        response = adapter.invoke("Explain this error")
        assert response.structured_data.intent == "EXPLAIN_ERROR"
        assert response.retries_used == 2

    def test_adapter_exhausted_retries_raises(self):
        """Verify LLMRetryExhaustedError when failures exceed max_retries."""
        # Fails 5 times, but max_retries is only 2
        mock_client = MockLLMClient(fail_count=5)
        adapter = LLMAdapter(client=mock_client, max_retries=2, initial_delay_seconds=0.01)

        with pytest.raises(LLMRetryExhaustedError, match="Exhausted 2 retries"):
            adapter.invoke("Explain error")

    def test_adapter_timeout_raises(self):
        """Verify LLMTimeoutError when client call exceeds timeout."""
        mock_client = MockLLMClient(simulate_timeout=True)
        adapter = LLMAdapter(client=mock_client, max_retries=1, initial_delay_seconds=0.01)

        with pytest.raises(LLMTimeoutError, match="exceeded timeout"):
            adapter.invoke("Calculate 1 + 1")

    def test_adapter_fallback_on_failure(self):
        """Verify fallback_on_failure=True yields nominal response without raising."""
        mock_client = MockLLMClient(simulate_timeout=True)
        adapter = LLMAdapter(
            client=mock_client,
            max_retries=1,
            initial_delay_seconds=0.01,
            fallback_on_failure=True,
        )

        response = adapter.invoke("What is 2 + 2?")
        assert response.structured_data is not None
        assert response.structured_data.intent == "DEFAULT_CONVERSATION"
        assert response.metadata.get("fallback") is True


# =============================================================================
# 5. Malformed Output Tests (Explicit Acceptance Criteria)
# =============================================================================

class TestMalformedOutputHandling:
    """Verifies malformed JSON, missing required fields, and type violations are caught."""

    def test_malformed_invalid_json_syntax(self):
        """Verify MalformedOutputError is raised when model output is unparseable JSON."""
        client = MockLLMClient(malformed_mode="invalid_json")
        adapter = LLMAdapter(client=client, max_retries=0)

        with pytest.raises(MalformedOutputError, match="invalid JSON"):
            adapter.invoke("Hello Co-Pilot")

    def test_malformed_missing_required_fields(self):
        """Verify MalformedOutputError is raised when required schema fields are missing."""
        client = MockLLMClient(malformed_mode="missing_fields")  # missing 'intent'
        adapter = LLMAdapter(client=client, max_retries=0)

        with pytest.raises(MalformedOutputError, match="failed ReasoningResult validation"):
            adapter.invoke("Find files")

    def test_malformed_invalid_data_types(self):
        """Verify MalformedOutputError is raised when field types violate schema."""
        client = MockLLMClient(malformed_mode="bad_types")  # boolean requires_tool is string
        adapter = LLMAdapter(client=client, max_retries=0)

        with pytest.raises(MalformedOutputError, match="validation:"):
            adapter.invoke("Calculate 5 + 5")

    def test_malformed_output_recovers_with_fallback(self):
        """Verify malformed outputs can be recovered safely via fallback mode."""
        client = MockLLMClient(malformed_mode="invalid_json")
        adapter = LLMAdapter(client=client, max_retries=0, fallback_on_failure=True)

        response = adapter.invoke("Summarize code")
        assert response.structured_data is not None
        assert response.structured_data.intent == "DEFAULT_CONVERSATION"
        assert "fallback" in response.metadata


# =============================================================================
# 6. End-to-End Week 2 Pipeline Integration Test
# =============================================================================

class TestWeek2PipelineIntegration:
    """Validates the full multimodal context pipeline and LLM adapter coordination."""

    def test_full_pipeline_flow(self):
        """
        Flow:
        1. Capture synthetic screen frame via CaptureAdapter (opt-in enabled).
        2. Run OCR via MockVisionAdapter.
        3. Bundle into ConversationContext.
        4. Assemble bounded, filtered context via ContextBuilder.
        5. Invoke LLM via LLMAdapter with structured output validation.
        """
        # 1. Capture Adapter
        capture_adapter = CaptureAdapter(CaptureConfig(capture_enabled=True))
        frame = capture_adapter.capture_frame(
            width=1280,
            height=720,
            visible_text="def calculate_roi(investment, return_val): return return_val / investment",
        )

        # 2. Vision Adapter (OCR)
        vision_adapter = MockVisionAdapter()
        vision_result = vision_adapter.process_frame(frame)
        assert "calculate_roi" in vision_result.extracted_text

        # 3. Context Bundling
        raw_ctx = ConversationContext(
            session_id="e2e-session-week2",
            active_window=WindowContext(
                app_name="VS Code",
                window_title="finance.py",
                visible_snippet=vision_result.extracted_text,
            ),
            user_query="Explain this error or calculate division",
            screen_context=frame,
            context_items=[
                ContextItem(
                    content="Investment calculation utilities",
                    source=SourceReference(source_id="finance.py", is_trusted=True),
                    is_trusted=True,
                )
            ],
        )

        # 4. Context Builder
        builder = ContextBuilder(ContextBuilderConfig(token_budget=1024))
        bounded_req = builder.build_context(raw_ctx)
        assert bounded_req.context is not None
        assert bounded_req.screen_context is not None

        # 5. LLM Adapter
        adapter = LLMAdapter(client=MockLLMClient())
        prompt = f"User Request: {bounded_req.query}\nSnippet: {bounded_req.context.active_window.visible_snippet}"
        llm_response = adapter.invoke(prompt, schema=ReasoningResult)

        assert isinstance(llm_response.structured_data, ReasoningResult)
        assert llm_response.structured_data.intent in ("EXPLAIN_ERROR", "CALCULATE", "DEFAULT_CONVERSATION")
        assert llm_response.structured_data.confidence > 0.0
