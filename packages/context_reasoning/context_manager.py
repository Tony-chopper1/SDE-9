import time
from typing import Optional
from packages.context_reasoning.models import ConversationContext, WindowContext


class ContextManager:
    """
    Tracks and updates active application context and conversation history.
    """
    def __init__(self, session_id: str):
        self._context = ConversationContext(
            session_id=session_id,
            active_window=WindowContext(
                app_name="VS Code",
                window_title="main.py - project",
                app_type="ide",
                visible_snippet="ImportError: No module named 'fastapi'",
            ),
            user_query="",
            history=[],
            timestamp=time.time(),
        )

    def update_user_query(self, query: str, visible_snippet: Optional[str] = None) -> ConversationContext:
        self._context.user_query = query
        if visible_snippet:
            self._context.active_window.visible_snippet = visible_snippet
        self._context.timestamp = time.time()
        return self._context

    def add_turn(self, role: str, content: str) -> None:
        from packages.context_reasoning.models import ConversationTurn
        self._context.history.append(ConversationTurn(role=role, content=content))

    def get_context(self) -> ConversationContext:
        return self._context
