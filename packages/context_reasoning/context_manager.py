"""
Context Manager for AI Voice Co-Pilot.

Manages active OS window, screen context, conversation history, and provides
serialization/deserialization methods for cross-service state persistence.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Literal, Optional

from packages.context_reasoning.models import (
    ConversationContext,
    ConversationTurn,
    WindowContext,
)


class ContextManager:
    """
    Manages active window, screen context, and conversation history.

    Features:
    - Thread-safe conversational turn accumulation with bounded sliding window.
    - Active OS window and code/screen snippet synchronization.
    - Serialization and state recovery from dictionary and JSON.
    - Formatted dialogue transcript generation for prompt injection.
    """

    def __init__(
        self,
        session_id: str,
        max_turns: int = 100,
        default_window: Optional[WindowContext] = None,
    ) -> None:
        """
        Initialize ContextManager for a given session.

        Args:
            session_id: Unique session identifier.
            max_turns: Maximum number of conversation turns to retain in memory.
            default_window: Optional custom initial window context.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string.")

        self.session_id: str = session_id
        self.max_turns: int = max(1, max_turns)
        self._context: ConversationContext = ConversationContext(
            session_id=session_id,
            active_window=default_window or WindowContext(),
            history=[],
            user_query="",
            timestamp=time.time(),
        )

    def update_user_query(
        self,
        query: str,
        visible_snippet: Optional[str] = None,
    ) -> ConversationContext:
        """
        Update context with a new user query and optional visible code/screen snippet.

        Args:
            query: The user's latest query or transcript string.
            visible_snippet: Optional code or document snippet currently visible on screen.

        Returns:
            Updated ConversationContext snapshot.
        """
        self._context.user_query = query
        self._context.timestamp = time.time()
        if visible_snippet is not None:
            self._context.active_window.visible_snippet = visible_snippet
        return self.get_context()

    def update_active_window(
        self,
        app_name: str,
        window_title: str,
        app_type: Literal["ide", "browser", "terminal", "document", "other"] = "ide",
        visible_snippet: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WindowContext:
        """
        Update active operating system window context.

        Args:
            app_name: Name of the application (e.g. 'VS Code', 'Chrome').
            window_title: Title bar text of the focused window.
            app_type: Application category.
            visible_snippet: Code or screen text snippet currently visible.
            url: Optional browser URL.
            metadata: Additional contextual key-value pairs.

        Returns:
            Updated WindowContext.
        """
        window = WindowContext(
            app_name=app_name,
            window_title=window_title,
            app_type=app_type,
            visible_snippet=visible_snippet,
            url=url,
            metadata=metadata or {},
        )
        self._context.active_window = window
        self._context.timestamp = time.time()
        return window

    def add_turn(
        self,
        role: Literal["user", "assistant", "system"],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationTurn:
        """
        Append a message turn to conversation history.

        Args:
            role: 'user', 'assistant', or 'system'.
            content: The text content of the message.
            metadata: Optional metadata dictionary.

        Returns:
            Created ConversationTurn.
        """
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role '{role}'. Must be 'user', 'assistant', or 'system'.")
        if not content:
            raise ValueError("Turn content cannot be empty.")

        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._context.history.append(turn)

        # Enforce sliding window bounds to prevent memory bloat
        if len(self._context.history) > self.max_turns:
            excess = len(self._context.history) - self.max_turns
            self._context.history = self._context.history[excess:]

        self._context.timestamp = time.time()
        return turn

    def get_context(self) -> ConversationContext:
        """
        Retrieve a snapshot of the current conversational context.

        Returns:
            A deep copy of the ConversationContext model.
        """
        return ConversationContext.model_validate(self._context.model_dump())

    def clear_history(self) -> None:
        """Clear all turns from the conversation history."""
        self._context.history.clear()
        self._context.timestamp = time.time()

    def reset(self) -> None:
        """Reset conversation history, query, and timestamps while retaining session ID."""
        self._context.history.clear()
        self._context.user_query = ""
        self._context.active_window = WindowContext()
        self._context.timestamp = time.time()

    def get_history_summary(self, max_turns: Optional[int] = None) -> str:
        """
        Generate a formatted dialogue string of recent turns for LLM prompt injection.

        Args:
            max_turns: Maximum number of recent turns to include. Defaults to all turns.

        Returns:
            Formatted transcript string (e.g., 'User: ...\nAssistant: ...').
        """
        history = self._context.history
        if max_turns and max_turns > 0:
            history = history[-max_turns:]

        lines: List[str] = []
        for turn in history:
            role_label = turn.role.capitalize()
            lines.append(f"{role_label}: {turn.content}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize current context to a Python dictionary."""
        return self._context.model_dump()

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialize current context to a JSON string."""
        return self._context.model_dump_json(indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_turns: int = 100) -> ContextManager:
        """
        Restore a ContextManager instance from a dictionary.

        Args:
            data: Serialized ConversationContext dictionary.
            max_turns: Max turns limit for the restored manager.

        Returns:
            Restored ContextManager instance.
        """
        context = ConversationContext.model_validate(data)
        manager = cls(session_id=context.session_id, max_turns=max_turns)
        manager._context = context
        return manager

    @classmethod
    def from_json(cls, json_str: str, max_turns: int = 100) -> ContextManager:
        """
        Restore a ContextManager instance from a JSON string.

        Args:
            json_str: Valid JSON string representation of ConversationContext.
            max_turns: Max turns limit for the restored manager.

        Returns:
            Restored ContextManager instance.
        """
        data = json.loads(json_str)
        return cls.from_dict(data, max_turns=max_turns)
