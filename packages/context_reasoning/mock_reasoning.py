"""
Mock Reasoning Service - Starter Template
Assigned Member: Praveen Kumar R (feature/context-reasoning - Task W3)
"""
from packages.context_reasoning.models import ConversationContext, ReasoningResult


class MockReasoningService:
    """
    Mock LLM Reasoning Service that classifies intent from user queries & active context.
    
    TODO (Praveen Kumar R):
    1. Inspect context.user_query and determine intent.
    2. If user asks about an error, return intent='EXPLAIN_ERROR' with a direct response.
    3. If user asks to search or move files, return intent='FILE_SEARCH' and set requires_tool=True.
    4. Return structured ReasoningResult.
    """
    def reason(self, context: ConversationContext) -> ReasoningResult:
        """Classify user intent and determine if tools are needed."""
        raise NotImplementedError("TODO: Praveen Kumar R - Implement reason")
