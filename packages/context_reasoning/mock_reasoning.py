from packages.context_reasoning.models import ConversationContext, ReasoningResult


class MockReasoningService:
    """
    Mock LLM Reasoning Service that classifies intent from user queries & active context.
    """
    def reason(self, context: ConversationContext) -> ReasoningResult:
        query_lower = context.user_query.lower()

        if "error" in query_lower or "failing" in query_lower:
            return ReasoningResult(
                intent="EXPLAIN_ERROR",
                requires_tool=False,
                direct_response=(
                    f"The error in {context.active_window.app_name} indicates an import issue. "
                    "Make sure your virtual environment has the package installed."
                ),
                confidence=0.96,
            )

        if "find" in query_lower or "search" in query_lower:
            return ReasoningResult(
                intent="FILE_SEARCH",
                requires_tool=True,
                planned_tool_name="file.search",
                tool_parameters={"query": "report"},
                direct_response=None,
                confidence=0.92,
            )

        return ReasoningResult(
            intent="GENERAL_ASSIST",
            requires_tool=False,
            direct_response=(
                f"I see you are in {context.active_window.app_name}. How can I assist you with this?"
            ),
            confidence=0.89,
        )
