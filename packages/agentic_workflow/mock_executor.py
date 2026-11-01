"""
Mock Tool Executor for the Agentic Workflow module.

Simulates the execution of registered tools (file search, file move, and
calculator evaluation) for integration testing and local development without
requiring real filesystem access or external services.

All tools are dispatched through a single :meth:`MockToolExecutor.execute`
entry-point and return a structured :class:`~packages.agentic_workflow.models.ToolResult`.
"""

from __future__ import annotations

import ast
import operator
import time
from typing import Any, Dict

from packages.agentic_workflow.models import ToolResult

# ---------------------------------------------------------------------------
# Safe math expression evaluator
# ---------------------------------------------------------------------------

# Mapping of AST node types to safe arithmetic operators
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
    """Simulates tool executions for agentic workflow integration testing.

    Registered tools:

    * ``file.search`` – Simulates a directory scan and returns mock matching paths.
    * ``file.move`` – Validates source/destination and returns a simulated move confirmation.
    * ``calc.evaluate`` – Safely evaluates arithmetic expressions and returns the result.

    Unknown tool names are handled gracefully with a descriptive :class:`ToolResult`
    containing ``success=False``.

    Args:
        simulate_failure: When ``True``, every :meth:`execute` call raises a
            simulated runtime error, allowing callers to test failure-recovery
            paths without targeting specific tools.

    Example::

        executor = MockToolExecutor()
        result = executor.execute("file.search", {"pattern": "*.py", "directory": "/src"})
        assert result.success is True
        assert isinstance(result.output["matches"], list)
        assert result.duration_ms >= 0
    """

    def __init__(self, simulate_failure: bool = False) -> None:
        self.simulate_failure = simulate_failure

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a named tool with the provided parameters.

        Dispatches to the appropriate private handler based on *tool_name*.
        Measures and records wall-clock execution time in milliseconds.

        Args:
            tool_name: Dot-namespaced tool identifier (e.g. ``"file.search"``).
            parameters: Keyword arguments consumed by the target tool.

        Returns:
            A :class:`~packages.agentic_workflow.models.ToolResult` with
            ``success``, ``output``, ``duration_ms``, and optionally ``error``.
        """
        start = time.perf_counter()

        if self.simulate_failure:
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error="Simulated tool failure (simulate_failure=True)",
            )

        try:
            output = self._dispatch(tool_name, parameters)
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """Route *tool_name* to the appropriate handler.

        Args:
            tool_name: Dot-namespaced tool identifier.
            parameters: Tool-specific keyword arguments.

        Returns:
            The raw output produced by the handler.

        Raises:
            ValueError: If *tool_name* is not a registered tool.
        """
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
    # Tool handlers
    # ------------------------------------------------------------------

    def _file_search(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a directory scan and return mock matching file paths.

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

        # Generate deterministic mock paths
        mock_files = [
            f"{directory.rstrip('/')}/mock_{i + 1}.{ext}" for i in range(min(max_results, 5))
        ]

        return {
            "matches": mock_files,
            "pattern": pattern,
            "directory": directory,
            "total_found": len(mock_files),
        }

    def _file_move(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate moving a file from source to destination.

        Recognised parameters:
            source (str): Absolute source file path. **Required.**
            destination (str): Absolute destination file path. **Required.**
            overwrite (bool): Whether to overwrite an existing destination (default: ``False``).

        Returns:
            A dict with keys:
                * ``source`` – original file path.
                * ``destination`` – new file path.
                * ``overwrite`` – whether overwrite was requested.
                * ``status`` – always ``"moved"`` on success.

        Raises:
            ValueError: If ``source`` or ``destination`` is missing or empty.
        """
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
        """Safely evaluate an arithmetic expression and return the result.

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
