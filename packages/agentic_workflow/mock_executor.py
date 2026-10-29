"""
Mock Tool Executor - Starter Template
Assigned Member: Chiranthan Rk (feature/agentic-workflow - Task W4)
"""
from typing import Any, Dict
from packages.agentic_workflow.models import ToolResult


class MockToolExecutor:
    """
    Simulates tool executions (e.g. file search, file read, file move, calculator).
    
    TODO (Chiranthan Rk):
    1. Implement execute method to handle registered tool names:
       - 'file.search': returns mock list of matching filenames.
       - 'file.move': returns mock confirmation with source & destination.
       - 'calc.evaluate': evaluates simple expressions or returns numeric result.
    2. Return structured ToolResult with success flag and execution duration.
    """
    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Execute mock tool action."""
        raise NotImplementedError("TODO: Chiranthan Rk - Implement execute")
