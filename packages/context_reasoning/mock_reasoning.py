"""
Mock LLM Reasoning Service for AI Voice Co-Pilot.

Simulates contextual natural language understanding, intent classification,
and tool parameter extraction without requiring external paid LLM credentials.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from packages.context_reasoning.models import ConversationContext, ReasoningResult


class MockReasoningService:
    """
    Mock LLM Reasoning Service that classifies intent from user queries & active context.

    Features:
    - Rule-based intent detection covering code explanations, error debugging,
      file operations, and mathematical calculations.
    - Contextual awareness incorporating active window and visible text snippets.
    - Deterministic tool parameter synthesis matching agentic workflow contracts.
    - Multi-step reasoning traces for transparency and debugging.
    """

    def __init__(self, confidence_threshold: float = 0.70) -> None:
        """
        Initialize the reasoning service.

        Args:
            confidence_threshold: Minimum confidence score for tool triggering.
        """
        self.confidence_threshold: float = confidence_threshold

    def reason(self, context: ConversationContext) -> ReasoningResult:
        """
        Classify user intent and determine if tools are needed.

        Args:
            context: Current ConversationContext containing user_query, active_window,
                     and conversation history.

        Returns:
            Structured ReasoningResult containing intent, tool invocation plan,
            direct response, confidence score, and explainable reasoning steps.
        """
        query = (context.user_query or "").strip()
        query_lower = query.lower()
        active_window = context.active_window
        snippet = active_window.visible_snippet or ""
        steps: List[str] = [f"Received query: '{query}'"]
        steps.append(f"Context: App='{active_window.app_name}', Title='{active_window.window_title}'")

        if not query:
            steps.append("Empty query detected; returning default idle response.")
            return ReasoningResult(
                intent="IDLE",
                requires_tool=False,
                direct_response="I'm listening. How can I assist you with your project today?",
                confidence=0.99,
                reasoning_steps=steps,
            )

        # 1. Error Explanation & Debugging Intent
        if re.search(r"\b[a-zA-Z]*error\b|\b(traceback|exception|crash|fail[a-z]*|bug|broken)\b", query_lower):
            steps.append("Matched error diagnostic keywords -> Intent: EXPLAIN_ERROR")
            explanation = self._generate_error_explanation(query, snippet, active_window.app_name)
            steps.append("Synthesized direct explanation from error context.")
            return ReasoningResult(
                intent="EXPLAIN_ERROR",
                requires_tool=False,
                planned_tool_name=None,
                tool_parameters=None,
                direct_response=explanation,
                confidence=0.96,
                reasoning_steps=steps,
            )

        # 2. File Search Intent
        if any(term in query_lower for term in ("search for", "find file", "look for file", "locate file", "search file", "find all")):
            steps.append("Matched file search keywords -> Intent: FILE_SEARCH")
            pattern = self._extract_search_pattern(query)
            steps.append(f"Extracted file search pattern: '{pattern}'")
            return ReasoningResult(
                intent="FILE_SEARCH",
                requires_tool=True,
                planned_tool_name="file.search",
                tool_parameters={"pattern": pattern, "directory": "."},
                direct_response=f"Searching for files matching '{pattern}' across the repository.",
                confidence=0.95,
                reasoning_steps=steps,
            )

        # 3. File Move / Relocate Intent
        if re.search(r"\b(move|relocate|rename)\b", query_lower) and any(kw in query_lower for kw in (" to ", " as ", "file")):
            steps.append("Matched file move/rename keywords -> Intent: FILE_MOVE")
            source, destination = self._extract_move_paths(query)
            steps.append(f"Extracted source='{source}', destination='{destination}'")
            return ReasoningResult(
                intent="FILE_MOVE",
                requires_tool=True,
                planned_tool_name="file.move",
                tool_parameters={"source": source, "destination": destination},
                direct_response=f"Moving '{source}' to '{destination}'. This operation requires confirmation.",
                confidence=0.93,
                reasoning_steps=steps,
            )

        # 4. Calculation Intent
        if (re.search(r"\b(calculate|compute|evaluate)\b", query_lower) or query_lower.startswith("what is ")) and re.search(r"\d", query):
            steps.append("Matched calculation keywords with numeric operands -> Intent: CALCULATE")
            expression = self._extract_math_expression(query)
            steps.append(f"Extracted math expression: '{expression}'")
            return ReasoningResult(
                intent="CALCULATE",
                requires_tool=True,
                planned_tool_name="calc.evaluate",
                tool_parameters={"expression": expression},
                direct_response=f"Evaluating mathematical expression: {expression}",
                confidence=0.97,
                reasoning_steps=steps,
            )

        # 5. Code Summarization & Explanation
        if any(term in query_lower for term in ("summarize", "explain this code", "explain the code", "what does this do", "what is this code")):
            steps.append("Matched code explanation keywords -> Intent: SUMMARIZE_CODE")
            summary = self._generate_code_summary(snippet, active_window.app_name)
            steps.append("Generated code summary using visible editor snippet.")
            return ReasoningResult(
                intent="SUMMARIZE_CODE",
                requires_tool=False,
                planned_tool_name=None,
                tool_parameters=None,
                direct_response=summary,
                confidence=0.94,
                reasoning_steps=steps,
            )

        # 6. General Greeting or Assistant Help
        if re.search(r"\b(hello|hi|hey|help|who are you|what can you do)\b", query_lower):
            steps.append("Matched conversational assistance keywords -> Intent: GENERAL_CONVERSATION")
            return ReasoningResult(
                intent="GENERAL_CONVERSATION",
                requires_tool=False,
                planned_tool_name=None,
                tool_parameters=None,
                direct_response=(
                    "Hello! I am your AI Voice Co-Pilot. I can help you inspect errors on your screen, "
                    "search or move files, run calculations, and summarize code."
                ),
                confidence=0.98,
                reasoning_steps=steps,
            )

        # 7. Fallback / Default Intent
        steps.append("No specific tool or diagnostic rule triggered -> Intent: DEFAULT_CONVERSATION")
        fallback_msg = f"I understood your request: '{query}'. In the active application ({active_window.app_name}), everything appears nominal."
        return ReasoningResult(
            intent="DEFAULT_CONVERSATION",
            requires_tool=False,
            planned_tool_name=None,
            tool_parameters=None,
            direct_response=fallback_msg,
            confidence=0.85,
            reasoning_steps=steps,
        )

    # -------------------------------------------------------------------------
    # Helper Parsing Methods
    # -------------------------------------------------------------------------

    def _extract_search_pattern(self, query: str) -> str:
        """Extract a glob pattern or file name from a search query."""
        match = re.search(r"(?:search for|find file|locate file|look for)\s+([\"']?)([\w\.\*\-\_]+)\1", query, re.IGNORECASE)
        if match:
            return match.group(2)
        # Default wildcard search based on last word
        tokens = query.split()
        return tokens[-1] if tokens else "*.py"

    def _extract_move_paths(self, query: str) -> Tuple[str, str]:
        """Extract source and destination paths from a file move query."""
        match = re.search(r"move\s+([^\s]+)\s+to\s+([^\s]+)", query, re.IGNORECASE)
        if match:
            return match.group(1).strip("\"'"), match.group(2).strip("\"'")
        return "source.txt", "destination.txt"

    def _extract_math_expression(self, query: str) -> str:
        """Extract arithmetic expression from a query string."""
        cleaned = re.sub(r"(?i)(calculate|compute|evaluate|what is|please)\s*", "", query).strip()
        cleaned = cleaned.rstrip("?").strip()
        # Find expression substring containing numbers and operators
        expr_match = re.search(r"[\d\.\s\+\-\*\/\(\)\^%]+", cleaned)
        if expr_match:
            return expr_match.group(0).strip()
        return cleaned or "0"

    def _generate_error_explanation(self, query: str, snippet: str, app_name: str) -> str:
        """Produce an analytical explanation of an error based on available snippet."""
        if "IndexError" in snippet or "IndexError" in query:
            return "The error is an IndexError: list index out of range. Check that the collection is not empty before indexing."
        if "KeyError" in snippet or "KeyError" in query:
            return "The error is a KeyError: the accessed dictionary key does not exist. Consider using dict.get() with a default value."
        if "TypeError" in snippet or "TypeError" in query:
            return "A TypeError occurred due to an unexpected operand type. Verify variable types prior to the operation."
        if snippet:
            return f"In your {app_name} editor, the active snippet contains an issue related to: '{query}'. Review the stack trace around line boundaries."
        return f"Detected an error condition from your query '{query}'. Check the application terminal or console output for detailed traceback logs."

    def _generate_code_summary(self, snippet: str, app_name: str) -> str:
        """Produce a high-level summary of the visible code snippet."""
        if not snippet or snippet.strip() == "(No visible code snippet)":
            return f"Your {app_name} editor currently has no visible code snippet selected to summarize."
        line_count = len(snippet.strip().splitlines())
        return f"The active snippet in {app_name} spans {line_count} lines of code. It defines module routines and data structures for the current workspace."
