"""
Mock Tool Executor for the Agentic Workflow module.

Simulates the execution of registered tools (file search, file move, and
calculator evaluation) for integration testing and local development without
requiring real filesystem access or external services.

Week 2 enhancements:
    * Per-step execution timeouts.
    * Bounded retries (up to 3 attempts with exponential backoff) for idempotent tools.
    * Suppression of retries for non-idempotent tools.
    * Cancellation support (cancel() / reset_cancellation()).
"""

from __future__ import annotations

import ast
import operator
import threading
import time
from typing import Any, Collection, Dict, Optional

from packages.agentic_workflow.models import (
    PermissionScope,
    ToolResult,
    WorkflowStep,
)
from packages.agentic_workflow.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolParameterError,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ExecutionCancelledError(Exception):
    """Raised or reported when tool execution is cancelled."""


class ToolExecutionTimeoutError(Exception):
    """Raised or reported when tool execution exceeds its allocated timeout."""


# ---------------------------------------------------------------------------
# Safe math expression evaluator
# ---------------------------------------------------------------------------

_SAFE_OPERATORS: Dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}


def _safe_eval(node: ast.expr) -> float:
    """Recursively evaluate a parsed AST expression using only safe operators."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _SAFE_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return _SAFE_OPERATORS[op_type](operand)

    raise ValueError(f"Unsupported AST node type: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Mock Tool Executor
# ---------------------------------------------------------------------------


class MockToolExecutor:
    """Simulates tool executions for agentic workflow integration testing.

    Registered default tools:
        * ``file.search`` – Simulates a directory scan and returns mock matching paths.
        * ``file.move`` – Validates source/destination and returns simulated move confirmation.
        * ``calc.evaluate`` – Safely evaluates arithmetic expressions and returns the result.

    Features:
        * Per-step timeout enforcement.
        * Bounded exponential-backoff retries for idempotent tools.
        * Immediate fail-fast (no retry) for non-idempotent tools.
        * Safe cooperative cancellation.
        * Parameter schema and permission scope checks via :class:`ToolRegistry`.
    """

    def __init__(
        self,
        simulate_failure: bool = False,
        registry: Optional[ToolRegistry] = None,
        default_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.simulate_failure = simulate_failure
        self.registry = registry or ToolRegistry()
        self.default_timeout_seconds = default_timeout_seconds
        self._cancelled: bool = False
        self._cancellation_reason: Optional[str] = None
        self._fail_first_n_attempts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Cancellation Controls
    # ------------------------------------------------------------------

    def cancel(self, reason: str = "Execution cancelled by operator") -> None:
        """Cancel current and subsequent tool executions."""
        self._cancelled = True
        self._cancellation_reason = reason

    def reset_cancellation(self) -> None:
        """Reset cancellation status to allow new executions."""
        self._cancelled = False
        self._cancellation_reason = None

    @property
    def is_cancelled(self) -> bool:
        """Check whether the executor is in a cancelled state."""
        return self._cancelled

    def set_fail_first_n_attempts(self, tool_name: str, count: int) -> None:
        """Helper for testing retries: fail the first N attempts of a tool before succeeding."""
        self._fail_first_n_attempts[tool_name] = count

    # ------------------------------------------------------------------
    # Single-Attempt Invocation
    # ------------------------------------------------------------------

    def _execute_single_attempt(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
    ) -> ToolResult:
        """Perform a single invocation of *tool_name* without retries."""
        start = time.perf_counter()

        if self.is_cancelled:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=0.0,
                error=f"Execution cancelled: {self._cancellation_reason}",
            )

        # Check programmed temporary failure count
        if self._fail_first_n_attempts.get(tool_name, 0) > 0:
            self._fail_first_n_attempts[tool_name] -= 1
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=f"Transient simulated error for {tool_name}",
            )

        if self.simulate_failure:
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error="Simulated tool failure (simulate_failure=True)",
            )

        # Check timeout configuration
        effective_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else parameters.get("timeout_seconds", self.default_timeout_seconds)
        )

        simulated_delay = parameters.get("simulated_delay", 0.0)

        result_container: Dict[str, Any] = {}
        exception_container: Dict[str, Exception] = {}

        def run_target():
            try:
                if simulated_delay > 0:
                    time.sleep(simulated_delay)
                result_container["output"] = self._dispatch(tool_name, parameters)
            except Exception as exc:
                exception_container["error"] = exc

        if effective_timeout is not None and effective_timeout > 0:
            worker = threading.Thread(target=run_target, daemon=True)
            worker.start()
            worker.join(timeout=effective_timeout)
            duration_ms = (time.perf_counter() - start) * 1000

            if worker.is_alive():
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    output=None,
                    duration_ms=duration_ms,
                    error=f"Tool execution timed out after {effective_timeout}s",
                )
        else:
            run_target()
            duration_ms = (time.perf_counter() - start) * 1000

        if "error" in exception_container:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=str(exception_container["error"]),
            )

        return ToolResult(
            tool_name=tool_name,
            success=True,
            output=result_container.get("output"),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Public execute interface (with Retry & Timeout Logic)
    # ------------------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
        is_idempotent: Optional[bool] = None,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.01,
        granted_scopes: Optional[Collection[PermissionScope]] = None,
    ) -> ToolResult:
        """Execute a named tool with retry resilience, timeout, and cancellation guards.

        Args:
            tool_name: Dot-namespaced tool identifier.
            parameters: Arguments passed to the tool.
            timeout_seconds: Optional per-invocation timeout limit in seconds.
            is_idempotent: Whether this tool invocation is safe to retry.
                If None, determined by querying the :class:`ToolRegistry`.
            max_retries: Maximum total attempts (1 initial + up to max_retries - 1 retries).
                         Default 3 total attempts.
            backoff_base_seconds: Multiplier for exponential backoff delay.
            granted_scopes: Optional permission scopes to enforce.

        Returns:
            A :class:`ToolResult` capturing success, output, duration, and error.
        """
        # 1. Cancellation check
        if self.is_cancelled:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=0.0,
                error=f"Execution cancelled: {self._cancellation_reason}",
            )

        # 2. Scope enforcement if scopes were passed
        if granted_scopes is not None:
            try:
                self.registry.enforce_permission(tool_name, granted_scopes)
            except (ToolNotFoundError, PermissionDeniedError) as err:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    output=None,
                    duration_ms=0.0,
                    error=str(err),
                )

        # 3. Determine idempotency
        if is_idempotent is None:
            if self.registry.is_registered(tool_name):
                is_idempotent = self.registry.get_spec(tool_name).is_idempotent
            else:
                is_idempotent = False

        # Non-idempotent tools strictly get 1 attempt (0 retries)
        allowed_attempts = max(1, max_retries) if is_idempotent else 1

        last_result: Optional[ToolResult] = None
        for attempt in range(1, allowed_attempts + 1):
            if self.is_cancelled:
                return ToolResult(
                    tool_name=tool_name,
                    success=False,
                    output=None,
                    duration_ms=0.0,
                    error=f"Execution cancelled: {self._cancellation_reason}",
                )

            last_result = self._execute_single_attempt(
                tool_name=tool_name,
                parameters=parameters,
                timeout_seconds=timeout_seconds,
            )

            if last_result.success:
                return last_result

            # If failed and more attempts remain for idempotent tool, backoff
            if attempt < allowed_attempts:
                delay = backoff_base_seconds * (2 ** (attempt - 1))
                time.sleep(delay)

        return last_result if last_result is not None else ToolResult(
            tool_name=tool_name,
            success=False,
            output=None,
            duration_ms=0.0,
            error="No execution attempts made.",
        )

    # ------------------------------------------------------------------
    # Step Execution Helper
    # ------------------------------------------------------------------

    def execute_step(
        self,
        step: WorkflowStep,
        granted_scopes: Optional[Collection[PermissionScope]] = None,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.01,
    ) -> ToolResult:
        """Execute a full :class:`WorkflowStep`, recording metadata and lifecycle status."""
        step.status = "running"
        step.started_at = time.time()
        step.execution_logs.append(
            f"[{step.started_at}] Started execution for step '{step.id}' ({step.tool_name})."
        )

        effective_idempotent = step.is_idempotent
        if self.registry.is_registered(step.tool_name):
            effective_idempotent = (
                step.is_idempotent and self.registry.get_spec(step.tool_name).is_idempotent
            )

        allowed_attempts = max(1, max_retries) if effective_idempotent else 1
        last_result: Optional[ToolResult] = None

        for attempt in range(1, allowed_attempts + 1):
            if self.is_cancelled:
                step.status = "cancelled"
                step.error = f"Cancelled: {self._cancellation_reason}"
                step.completed_at = time.time()
                step.execution_logs.append(f"[{step.completed_at}] Execution cancelled.")
                return ToolResult(
                    tool_name=step.tool_name,
                    success=False,
                    output=None,
                    duration_ms=0.0,
                    error=step.error,
                )

            # Check parameter validation via registry
            if self.registry.is_registered(step.tool_name):
                try:
                    self.registry.validate_parameters(step.tool_name, step.parameters)
                except ToolParameterError as param_err:
                    step.status = "failed"
                    step.error = str(param_err)
                    step.completed_at = time.time()
                    step.execution_logs.append(f"[{step.completed_at}] Parameter validation error: {param_err}")
                    return ToolResult(
                        tool_name=step.tool_name,
                        success=False,
                        output=None,
                        duration_ms=0.0,
                        error=step.error,
                    )

            last_result = self.execute(
                tool_name=step.tool_name,
                parameters=step.parameters,
                timeout_seconds=step.timeout_seconds,
                is_idempotent=effective_idempotent,
                max_retries=1,  # execute_step handles loop counting for retry_count accuracy
                granted_scopes=granted_scopes,
            )

            if last_result.success:
                step.status = "completed"
                step.result = last_result.output
                step.completed_at = time.time()
                step.execution_logs.append(
                    f"[{step.completed_at}] Step completed in {last_result.duration_ms:.2f}ms."
                )
                return last_result

            # If attempt failed, update retry count
            if attempt < allowed_attempts:
                step.retry_count += 1
                delay = backoff_base_seconds * (2 ** (attempt - 1))
                step.execution_logs.append(
                    f"Attempt {attempt} failed ({last_result.error}). Retrying in {delay:.3f}s..."
                )
                time.sleep(delay)

        # All attempts exhausted
        step.status = "failed"
        step.error = last_result.error if last_result else "Execution failed."
        step.completed_at = time.time()
        step.execution_logs.append(f"[{step.completed_at}] Step failed: {step.error}")
        return last_result or ToolResult(
            tool_name=step.tool_name,
            success=False,
            output=None,
            duration_ms=0.0,
            error=step.error,
        )

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Route *tool_name* to the appropriate handler."""
        handlers = {
            "file.search": self._file_search,
            "file.move": self._file_move,
            "calc.evaluate": self._calc_evaluate,
        }
        if tool_name not in handlers:
            raise ValueError(
                f"Unknown tool '{tool_name}'. "
                f"Registered tools: {list(handlers.keys())}"
            )
        return handlers[tool_name](parameters)

    # ------------------------------------------------------------------
    # Tool Handlers
    # ------------------------------------------------------------------

    def _file_search(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a directory scan and return mock matching file paths."""
        pattern: str = parameters.get("pattern", "*")
        directory: str = parameters.get("directory", "/")
        max_results: int = int(parameters.get("max_results", 10))

        ext = pattern.lstrip("*").lstrip(".")
        ext = ext if ext else "file"

        mock_files = [
            f"{directory.rstrip('/')}/mock_{i + 1}.{ext}"
            for i in range(min(max_results, 5))
        ]

        return {
            "matches": mock_files,
            "pattern": pattern,
            "directory": directory,
            "total_found": len(mock_files),
        }

    def _file_move(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate moving a file from source to destination."""
        source: str = parameters.get("source", "")
        destination: str = parameters.get("destination", "")
        overwrite: bool = bool(parameters.get("overwrite", False))

        if not source:
            raise ValueError("file.move requires a non-empty 'source' parameter.")
        if not destination:
            raise ValueError("file.move requires a non-empty 'destination' parameter.")

        return {
            "source": source,
            "destination": destination,
            "overwrite": overwrite,
            "status": "moved",
        }

    def _calc_evaluate(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Safely evaluate an arithmetic expression and return the result."""
        expression: str = parameters.get("expression", "")

        if not expression:
            raise ValueError("calc.evaluate requires a non-empty 'expression' parameter.")

        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid expression syntax: {exc}") from exc

        result = _safe_eval(tree.body)
        return {
            "expression": expression,
            "result": result,
        }
