"""
Context Manager - Starter Template
Assigned Member: Praveen Kumar R (feature/context-reasoning - Task W3)
"""
from typing import Optional
from packages.context_reasoning.models import ConversationContext, WindowContext


class ContextManager:
    """
    Manages active window, screen context, and conversation history.
    
    TODO (Praveen Kumar R):
    1. Initialize ConversationContext with default active window info.
    2. Implement update_user_query to refresh the query and update timestamp.
    3. Implement add_turn to append user and assistant messages to history.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id

    def update_user_query(self, query: str, visible_snippet: Optional[str] = None) -> ConversationContext:
        """Update context with new query and optional visible code/screen snippet."""
        raise NotImplementedError("TODO: Praveen Kumar R - Implement update_user_query")

    def add_turn(self, role: str, content: str) -> None:
        """Append a turn (user/assistant/system) to conversation history."""
        raise NotImplementedError("TODO: Praveen Kumar R - Implement add_turn")

    def get_context(self) -> ConversationContext:
        """Retrieve the current context snapshot."""
        raise NotImplementedError("TODO: Praveen Kumar R - Implement get_context")
