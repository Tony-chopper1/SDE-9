"""
Mock Tool Executor for the Agentic Workflow module.

Simulates the execution of registered harmless tools (file search and
calculator evaluation) for integration testing and local development without
requiring real filesystem access, file modifications, or external services.

All tools are dispatched through a single :meth:`MockToolExecutor.execute`
entry-point and return a structured :class:`~packages.agentic_workflow.models.WorkflowResult`.

Week 2 enhancements:
    * Per-step execution timeouts.
    * Bounded retries (up to 3 attempts with exponential backoff) for idempotent tools.
    * Suppression of retries for non-idempotent tools.
    * Cancellation support (cancel() / reset_cancellation()).
    * Execution history tracking for zero-tool verification.
"""

from __future__ import annotations

import ast
import operator
import threading
import time
from typing import Any, Collection, Dict, List, Optional

from packages.agentic_workflow.models import (
    PermissionScope,
    SafetyLevel,
    ToolSpec,
    WorkflowResult,
    WorkflowStep,
)


# ---------------------------------------------------------------------------
# Allow-listed Harmless Tool Specifications
# ---------------------------------------------------------------------------

DEFAULT_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="file.search",
        description="Simulates searching for file paths matching a glob pattern.",
        safety_level=SafetyLevel.A,
        is_idempotent=True,
        parameters={"pattern": "str", "directory": "str", "max_results": "int"},
        required_parameters={},
        optional_parameters={"pattern": str, "directory": str, "max_results": int},
    ),
    ToolSpec(
        name="calc.evaluate",
        description="Safely evaluates basic arithmetic expressions.",
        safety_level=SafetyLevel.A,
        is_idempotent=True,
        parameters={"expression": "str"},
        required_parameters={"expression": str},
        optional_parameters={},
    ),
]


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
    """Recursively evaluate a parsed AST expression using only safe operators.

    Args:
        node: An :mod:`ast` expression node.

    Returns:
        The numeric result of the expression.

    Raises:
        ValueError: If the expression contains an unsupported construct.
    """
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
    """Simulates harmless tool executions for agentic workflow testing.

    Registered harmless tools:
    * ``file.search`` / ``file_search`` – Simulates a directory scan and returns mock matching paths.
    * ``calc.evaluate`` / ``calc_evaluate`` – Safely evaluates arithmetic expressions and returns the result.

    Note: Consequential tools like ``file.move`` have been removed to prevent
    unintended file modifications or external side-effects.

    Args:
        simulate_failure: When ``True``, every :meth:`execute` call returns a
            simulated failure, allowing callers to test failure-recovery paths.
        registry: Optional tool registry instance.
        default_timeout_seconds: Optional default timeout in seconds.
    """

    def __init__(
        self,
        simulate_failure: bool = False,
        registry: Optional[Any] = None,
        default_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.simulate_failure = simulate_failure
        self.registry = registry
        self.default_timeout_seconds = default_timeout_seconds
        self.specs: Dict[str, ToolSpec] = {spec.name: spec for spec in DEFAULT_TOOL_SPECS}
        self._cancelled: bool = False
        self._cancellation_reason: Optional[str] = None
        self._fail_first_n_attempts: Dict[str, int] = {}
        self.execution_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public interface & Cancellation Controls
    # ------------------------------------------------------------------

    def get_registered_tools(self) -> List[str]:
        """Return list of registered harmless tool names."""
        return list(self.specs.keys())

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
    ) -> WorkflowResult:
        """Perform a single invocation of *tool_name* without retries."""
        start = time.perf_counter()

        if self.is_cancelled:
            return WorkflowResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=0.0,
                error=f"Execution cancelled: {self._cancellation_reason}",
            )

        # Track that an execution attempt was dispatched
        self.execution_history.append({
            "tool_name": tool_name,
            "parameters": dict(parameters),
            "timestamp": time.time(),
        })

        # Check programmed temporary failure count
        if self._fail_first_n_attempts.get(tool_name, 0) > 0:
            self._fail_first_n_attempts[tool_name] -= 1
            duration_ms = (time.perf_counter() - start) * 1000
            return WorkflowResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=f"Transient simulated error for {tool_name}",
            )

        if self.simulate_failure:
            duration_ms = (time.perf_counter() - start) * 1000
            return WorkflowResult(
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
                return WorkflowResult(
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
            return WorkflowResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=str(exception_container["error"]),
            )

        return WorkflowResult(
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
        max_retries: int = 1,
        backoff_base_seconds: float = 0.01,
        granted_scopes: Optional[Collection[PermissionScope]] = None,
    ) -> WorkflowResult:
        """Execute a named harmless tool with retry resilience, timeout, and cancellation guards.

        Args:
            tool_name: Dot-namespaced tool identifier (e.g. ``"file.search"``).
            parameters: Key-value dictionary of arguments for the tool.
            timeout_seconds: Optional timeout in seconds.
            is_idempotent: Whether this tool invocation is safe to retry.
            max_retries: Maximum total attempts.
            backoff_base_seconds: Multiplier for exponential backoff delay.
            granted_scopes: Optional permission scopes to enforce.

        Returns:
            A :class:`~packages.agentic_workflow.models.WorkflowResult`.
        """
        if self.is_cancelled:
            return WorkflowResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=0.0,
                error=f"Execution cancelled: {self._cancellation_reason}",
            )

        # Enforce permission scopes if registry is available
        if granted_scopes is not None and self.registry is not None:
            try:
                self.registry.enforce_permission(tool_name, granted_scopes)
            except Exception as err:
                return WorkflowResult(
                    tool_name=tool_name,
                    success=False,
                    output=None,
                    duration_ms=0.0,
                    error=str(err),
                )

        # Determine idempotency
        if is_idempotent is None:
            if tool_name in self.specs:
                is_idempotent = self.specs[tool_name].is_idempotent
            elif self.registry is not None and self.registry.is_registered(tool_name):
                is_idempotent = self.registry.get_spec(tool_name).is_idempotent
            else:
                is_idempotent = False

        allowed_attempts = max(1, max_retries) if is_idempotent else 1
        last_result: Optional[WorkflowResult] = None

        for attempt in range(1, allowed_attempts + 1):
            if self.is_cancelled:
                return WorkflowResult(
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

            # If attempt failed and more attempts remain for idempotent tool, backoff
            if attempt < allowed_attempts:
                delay = backoff_base_seconds * (2 ** (attempt - 1))
                time.sleep(delay)

        return last_result if last_result is not None else WorkflowResult(
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
    ) -> WorkflowResult:
        """Execute a full :class:`WorkflowStep`, recording metadata and lifecycle status."""
        step.status = "running"
        step.started_at = time.time()
        step.execution_logs.append(
            f"[{step.started_at}] Started execution for step '{step.id}' ({step.tool_name})."
        )

        effective_idempotent = step.is_idempotent
        if self.registry is not None and self.registry.is_registered(step.tool_name):
            effective_idempotent = (
                step.is_idempotent and self.registry.get_spec(step.tool_name).is_idempotent
            )
        elif step.tool_name in self.specs:
            effective_idempotent = step.is_idempotent and self.specs[step.tool_name].is_idempotent

        allowed_attempts = max(1, max_retries) if effective_idempotent else 1
        last_result: Optional[WorkflowResult] = None

        for attempt in range(1, allowed_attempts + 1):
            if self.is_cancelled:
                step.status = "cancelled"
                step.error = f"Cancelled: {self._cancellation_reason}"
                step.completed_at = time.time()
                step.execution_logs.append(f"[{step.completed_at}] Execution cancelled.")
                return WorkflowResult(
                    tool_name=step.tool_name,
                    success=False,
                    output=None,
                    duration_ms=0.0,
                    error=step.error,
                )

            # Check parameter validation via registry if present
            if self.registry is not None and self.registry.is_registered(step.tool_name):
                try:
                    self.registry.validate_parameters(step.tool_name, step.parameters)
                except Exception as param_err:
                    step.status = "failed"
                    step.error = str(param_err)
                    step.completed_at = time.time()
                    step.execution_logs.append(f"[{step.completed_at}] Parameter validation error: {param_err}")
                    return WorkflowResult(
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
                max_retries=1,
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
        return last_result or WorkflowResult(
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
        """Route *tool_name* to the appropriate handler.

        Args:
            tool_name: Dot-namespaced or identifier tool name.
            parameters: Tool-specific keyword arguments.

        Returns:
            The raw output produced by the handler.

        Raises:
            ValueError: If *tool_name* is not an authorized harmless tool.
        """
        handlers = {
            "file.search": self._file_search,
            "file_search": self._file_search,
            "calc.evaluate": self._calc_evaluate,
            "calc_evaluate": self._calc_evaluate,
        }
        if tool_name not in handlers:
            # If tool is registered in the external registry (permission already enforced by caller),
            # return a mock success result to simulate delegated execution.
            if self.registry is not None and self.registry.is_registered(tool_name):
                return {
                    "tool": tool_name,
                    "status": "simulated_success",
                    "note": "Executed via registry delegation (mock)",
                }
            raise ValueError(
                f"Unknown tool '{tool_name}'. "
                f"Registered tools: ['file.search', 'calc.evaluate']"
            )
        return handlers[tool_name](parameters)

    # ------------------------------------------------------------------
    # Harmless Tool Handlers
    # ------------------------------------------------------------------

    def _file_search(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a directory scan and return mock matching file paths.

        Harmless mock tool: does not perform any real filesystem operations.

        Recognised parameters:
            pattern (str): Glob-style file pattern (e.g. ``"*.py"``).
            directory (str): Root directory to scan (default: ``"/"``).
            max_results (int): Maximum number of results to return (default: ``10``).

        Returns:
            A dict with keys:
                * ``matches`` – list of simulated matching file paths.
                * ``pattern`` – the pattern that was searched.
                * ``directory`` – the root directory that was scanned.
                * ``total_found`` – total number of matches returned.
        """
        pattern: str = parameters.get("pattern", "*")
        directory: str = parameters.get("directory", "/")
        max_results: int = int(parameters.get("max_results", 10))

        # Strip leading wildcard for extension extraction
        ext = pattern.lstrip("*").lstrip(".")
        ext = ext if ext else "file"

        # Generate deterministic mock paths (no real disk access)
        mock_files = [
            f"{directory.rstrip('/')}/mock_{i + 1}.{ext}" for i in range(min(max_results, 5))
        ]

        return {
            "matches": mock_files,
            "pattern": pattern,
            "directory": directory,
            "total_found": len(mock_files),
        }

    def _calc_evaluate(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Safely evaluate an arithmetic expression and return the result.

        Harmless mock tool: purely in-memory evaluation with no side-effects.

        Recognised parameters:
            expression (str): A mathematical expression string (e.g. ``"2 + 3 * 4"``).

        Supported operations: ``+``, ``-``, ``*``, ``/``, ``//``, ``%``, ``**``,
        unary ``-`` and ``+``, and integer/float literals.

        Returns:
            A dict with keys:
                * ``expression`` – the original expression string.
                * ``result`` – the numeric result (``float``).

        Raises:
            ValueError: If ``expression`` is missing, empty, or contains unsupported
                constructs (e.g. function calls, variable names, or string literals).
        """
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
