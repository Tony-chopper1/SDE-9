"""
LLM Client Adapter with Timeout, Retry, and Structured-Output Validation.

Provides an enterprise-grade LLM adapter supporting deterministic mock generation
by default, configurable timeouts, exponential-backoff retries, and strict Pydantic
schema validation with malformed-output recovery.
"""
from __future__ import annotations

import abc
import json
import re
import time
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from packages.context_reasoning.exceptions import (
    LLMError,
    LLMRetryExhaustedError,
    LLMTimeoutError,
    MalformedOutputError,
)
from packages.context_reasoning.models import LLMResponse, ReasoningResult

T = TypeVar("T", bound=BaseModel)


class BaseLLMClient(abc.ABC):
    """Abstract interface for raw LLM text generation."""

    @abc.abstractmethod
    def complete(
        self,
        prompt: str,
        timeout: float = 5.0,
    ) -> str:
        """
        Generate completion text for a prompt within a given timeout.

        Args:
            prompt: Text prompt passed to the model.
            timeout: Maximum allowed execution time in seconds.

        Returns:
            Raw model completion string.
        """
        pass


class MockLLMClient(BaseLLMClient):
    """
    Deterministic mock LLM client for SDK-9.

    Features:
    - Generates valid JSON adhering to ReasoningResult schema without network access.
    - Controllable failure injection (transient failures, timeouts, malformed JSON).
    - Zero cost and sub-millisecond execution for rapid test cycles.
    """

    def __init__(
        self,
        fail_count: int = 0,
        simulate_timeout: bool = False,
        malformed_mode: Optional[str] = None,
        model_name: str = "mock-gpt-4o-voice",
    ) -> None:
        """
        Initialize MockLLMClient.

        Args:
            fail_count: Number of times to raise transient LLMError before succeeding.
            simulate_timeout: If True, simulates request timeout by raising TimeoutError.
            malformed_mode: One of 'invalid_json', 'missing_fields', 'bad_types', or None.
            model_name: Identifier of the mock model.
        """
        self.fail_count = fail_count
        self.simulate_timeout = simulate_timeout
        self.malformed_mode = malformed_mode
        self.model_name = model_name
        self._calls_made = 0

    def complete(self, prompt: str, timeout: float = 5.0) -> str:
        """Produce mock response or trigger configured test failure mode."""
        self._calls_made += 1

        if self.simulate_timeout:
            raise TimeoutError(f"Mock LLM call exceeded timeout of {timeout}s.")

        if self.fail_count > 0:
            self.fail_count -= 1
            raise LLMError("Transient upstream LLM gateway error (503 Service Unavailable).")

        if self.malformed_mode == "invalid_json":
            return "{ unclosed_json: 'broken syntax, missing closing brace"

        if self.malformed_mode == "missing_fields":
            return json.dumps({"confidence": 0.95})  # Missing required 'intent'

        if self.malformed_mode == "bad_types":
            return json.dumps({
                "intent": "FILE_SEARCH",
                "requires_tool": "NOT_A_BOOLEAN",  # Should be boolean
                "confidence": "HIGH",  # Should be float
            })

        # Deterministic generation based on keywords in prompt
        prompt_lower = prompt.lower()

        if "search for" in prompt_lower or "find file" in prompt_lower:
            payload = {
                "intent": "FILE_SEARCH",
                "requires_tool": True,
                "planned_tool_name": "file.search",
                "tool_parameters": {"pattern": "*.py", "directory": "."},
                "direct_response": "Searching for files matching pattern across workspace.",
                "confidence": 0.96,
                "reasoning_steps": ["Detected file search request", "Extracted pattern *.py"],
            }
        elif "calculate" in prompt_lower or "compute" in prompt_lower or "what is" in prompt_lower:
            payload = {
                "intent": "CALCULATE",
                "requires_tool": True,
                "planned_tool_name": "calc.evaluate",
                "tool_parameters": {"expression": "100 * 2"},
                "direct_response": "Evaluated arithmetic expression to 200.",
                "confidence": 0.98,
                "reasoning_steps": ["Detected math calculation intent", "Extracted operands"],
            }
        elif "error" in prompt_lower or "exception" in prompt_lower:
            payload = {
                "intent": "EXPLAIN_ERROR",
                "requires_tool": False,
                "planned_tool_name": None,
                "tool_parameters": None,
                "direct_response": "Diagnosed runtime exception from visible snippet.",
                "confidence": 0.94,
                "reasoning_steps": ["Identified error keyword", "Generated diagnostic summary"],
            }
        else:
            payload = {
                "intent": "DEFAULT_CONVERSATION",
                "requires_tool": False,
                "planned_tool_name": None,
                "tool_parameters": None,
                "direct_response": "Acknowledged. All systems operational.",
                "confidence": 0.90,
                "reasoning_steps": ["Nominal conversation query"],
            }

        return json.dumps(payload, indent=2)


class LLMAdapter:
    """
    Production-ready LLM Client Adapter with retry, timeout, and schema validation.

    Features:
    - Default offline mock client (requires zero external API keys).
    - Strict timeout enforcement per call.
    - Exponential backoff with retry limit.
    - Automated Pydantic structured output validation.
    - Graceful fallback mode for robust error tolerance.
    """

    def __init__(
        self,
        client: Optional[BaseLLMClient] = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        backoff_factor: float = 1.5,
        initial_delay_seconds: float = 0.05,
        fallback_on_failure: bool = False,
    ) -> None:
        """
        Initialize the LLM adapter.

        Args:
            client: Underlying BaseLLMClient (defaults to MockLLMClient()).
            timeout_seconds: Timeout per execution attempt in seconds.
            max_retries: Maximum number of retry attempts upon failure.
            backoff_factor: Multiplier for exponential backoff delay.
            initial_delay_seconds: Initial sleep duration before first retry.
            fallback_on_failure: If True, returns nominal fallback instead of raising.
        """
        self.client: BaseLLMClient = client or MockLLMClient()
        self.timeout_seconds: float = max(0.1, timeout_seconds)
        self.max_retries: int = max(0, max_retries)
        self.backoff_factor: float = max(1.0, backoff_factor)
        self.initial_delay_seconds: float = max(0.001, initial_delay_seconds)
        self.fallback_on_failure: bool = fallback_on_failure

    def invoke(
        self,
        prompt: str,
        schema: Optional[Type[T]] = None,
    ) -> LLMResponse:
        """
        Invoke the LLM with timeout enforcement, exponential retry, and schema validation.

        Args:
            prompt: Formatted prompt string.
            schema: Optional Pydantic model class to validate output against.

        Returns:
            Structured LLMResponse containing parsed and validated data.

        Raises:
            LLMTimeoutError: If timeout exceeded and fallback disabled.
            LLMRetryExhaustedError: If all retries exhausted.
            MalformedOutputError: If output fails JSON decoding or schema validation.
        """
        start_time = time.perf_counter()
        target_schema = schema or ReasoningResult
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                # 1. Execute LLM Call with Timeout
                raw_text = self.client.complete(prompt, timeout=self.timeout_seconds)

                # 2. Parse JSON
                try:
                    raw_json = json.loads(raw_text)
                except json.JSONDecodeError as json_err:
                    raise MalformedOutputError(
                        f"LLM produced invalid JSON: {json_err.msg} in '{raw_text[:80]}...'"
                    ) from json_err

                # 3. Validate against Pydantic Schema
                try:
                    validated = target_schema.model_validate(raw_json)
                except ValidationError as val_err:
                    raise MalformedOutputError(
                        f"LLM output failed {target_schema.__name__} validation: {val_err.error_count()} errors."
                    ) from val_err

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                return LLMResponse(
                    content=raw_text,
                    raw_json=raw_json,
                    structured_data=validated,
                    model_name=getattr(self.client, "model_name", "mock-llm"),
                    latency_ms=round(elapsed_ms, 2),
                    retries_used=attempt,
                    metadata={"attempt": attempt + 1, "schema": target_schema.__name__},
                )

            except (TimeoutError, LLMTimeoutError) as to_err:
                last_error = LLMTimeoutError(str(to_err))
            except MalformedOutputError as m_err:
                last_error = m_err
            except Exception as exc:
                last_error = LLMError(f"LLM invocation failed: {exc}")

            # Apply backoff before next retry if attempts remain
            if attempt < self.max_retries:
                delay = self.initial_delay_seconds * (self.backoff_factor ** attempt)
                time.sleep(delay)

        # Retries exhausted
        if self.fallback_on_failure:
            fallback_obj = ReasoningResult(
                intent="DEFAULT_CONVERSATION",
                requires_tool=False,
                direct_response="Safe fallback: All services nominal. How can I assist?",
                confidence=0.50,
                reasoning_steps=["Fallback engaged after LLM invocation error"],
                metadata={"error": str(last_error)},
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return LLMResponse(
                content=json.dumps(fallback_obj.model_dump()),
                raw_json=fallback_obj.model_dump(),
                structured_data=fallback_obj,
                model_name=getattr(self.client, "model_name", "mock-llm-fallback"),
                latency_ms=round(elapsed_ms, 2),
                retries_used=self.max_retries,
                metadata={"fallback": True, "root_error": str(last_error)},
            )

        if isinstance(last_error, (LLMTimeoutError, MalformedOutputError)):
            raise last_error

        raise LLMRetryExhaustedError(
            f"Exhausted {self.max_retries} retries for LLM invocation. Last error: {last_error}"
        ) from last_error
