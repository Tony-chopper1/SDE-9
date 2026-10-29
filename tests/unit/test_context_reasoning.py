"""
Unit Tests for Context & Reasoning Module
Assigned Member: Praveen Kumar R (feature/context-reasoning - Task W3)

TODO (Praveen Kumar R):
Write unit tests for ContextManager, VersionedPromptManager, and MockReasoningService to achieve >80% coverage.
"""
import pytest
from packages.context_reasoning import WindowContext, ConversationContext, ReasoningResult


def test_context_models_instantiation():
    """Verify that Context models can be constructed."""
    win = WindowContext(app_name="VS Code", window_title="test.py")
    ctx = ConversationContext(session_id="s1", active_window=win)

    assert ctx.session_id == "s1"
    assert ctx.active_window.app_name == "VS Code"


# TODO (Praveen Kumar R): Uncomment and implement after completing context_manager.py and mock_reasoning.py
# def test_context_manager_updates():
#     cm = ContextManager("s1")
#     ...
