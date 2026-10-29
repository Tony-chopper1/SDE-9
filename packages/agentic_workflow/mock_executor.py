import time
from typing import Any, Dict
from packages.agentic_workflow.models import ToolResult


class MockToolExecutor:
    """
    Executes mock desktop tools simulating file search, file move, and calculation.
    """
    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        start_time = time.time()

        if tool_name == "file.search":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output={"matches": ["/home/user/docs/q3_report.pdf", "/home/user/docs/final_report.pdf"]},
                duration_ms=(time.time() - start_time) * 1000,
            )

        if tool_name == "file.move":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output={"moved": True, "source": parameters.get("source"), "destination": parameters.get("destination")},
                duration_ms=(time.time() - start_time) * 1000,
            )

        if tool_name == "calc.evaluate":
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output={"result": 42},
                duration_ms=(time.time() - start_time) * 1000,
            )

        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=None,
            duration_ms=(time.time() - start_time) * 1000,
            error=f"Tool '{tool_name}' not recognized.",
        )
