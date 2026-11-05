"""
Comprehensive Unit and Integration Tests for Context & Reasoning Module.

Validates schema models, context manager state tracking and serialization,
versioned prompt rendering, mock LLM reasoning decisions, and CLI simulation.
"""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from packages.context_reasoning.models import (
    ConversationContext,
    ConversationTurn,
    ReasoningResult,
    VersionedPromptTemplate,
    WindowContext,
)
from packages.context_reasoning.context_manager import ContextManager
from packages.context_reasoning.prompt_manager import VersionedPromptManager
from packages.context_reasoning.mock_reasoning import MockReasoningService
from packages.context_reasoning.cli import run_simulation


# =============================================================================
# 1. Domain Models Tests
# =============================================================================

class TestContextModels:
    """Tests for Pydantic models in models.py."""

    def test_window_context_defaults(self):
        """Verify default values for WindowContext."""
        win = WindowContext()
        assert win.app_name == "VS Code"
        assert win.window_title == "app.py - project"
        assert win.app_type == "ide"
        assert win.visible_snippet is None
        assert win.url is None
        assert win.metadata == {}

    def test_window_context_custom_values(self):
        """Verify custom values and extra fields handling."""
        win = WindowContext(
            app_name="Google Chrome",
            window_title="GitHub - SDK-9",
            app_type="browser",
            visible_snippet="<html><body>Voicebot</body></html>",
            url="https://github.com",
            metadata={"tab_id": 42},
        )
        assert win.app_name == "Google Chrome"
        assert win.app_type == "browser"
        assert win.url == "https://github.com"
        assert win.metadata["tab_id"] == 42

    def test_conversation_turn_creation(self):
        """Verify turn creation and unique turn IDs."""
        turn1 = ConversationTurn(role="user", content="Hello co-pilot")
        turn2 = ConversationTurn(role="assistant", content="How can I help?")

        assert turn1.role == "user"
        assert turn1.content == "Hello co-pilot"
        assert turn1.id != turn2.id
        assert turn1.timestamp > 0

    def test_conversation_context_defaults(self):
        """Verify default initialization of ConversationContext."""
        ctx = ConversationContext(session_id="session-123")
        assert ctx.session_id == "session-123"
        assert ctx.active_window.app_name == "VS Code"
        assert ctx.history == []
        assert ctx.user_query == ""
        assert ctx.timestamp > 0

    def test_versioned_prompt_template_model(self):
        """Verify VersionedPromptTemplate attributes."""
        template = VersionedPromptTemplate(
            version="v3.0",
            template="Prompt: {query}",
            variables=["query"],
            description="Test template",
        )
        assert template.version == "v3.0"
        assert template.variables == ["query"]
        assert template.description == "Test template"

    def test_reasoning_result_confidence_validation(self):
        """Verify confidence bounds in ReasoningResult."""
        res = ReasoningResult(
            intent="FILE_SEARCH",
            requires_tool=True,
            planned_tool_name="file.search",
            confidence=0.92,
        )
        assert res.confidence == 0.92
        assert res.requires_tool is True

        with pytest.raises(ValidationError):
            ReasoningResult(intent="TEST", requires_tool=False, confidence=1.5)


# =============================================================================
# 2. Context Manager Tests
# =============================================================================

class TestContextManager:
    """Tests for ContextManager state tracking, sliding window, and serialization."""

    def test_initialization_validation(self):
        """Verify that empty or whitespace session ID raises ValueError."""
        with pytest.raises(ValueError, match="session_id must be a non-empty string"):
            ContextManager(session_id="")
        with pytest.raises(ValueError):
            ContextManager(session_id="   ")

    def test_update_user_query(self):
        """Verify query and snippet updating."""
        cm = ContextManager("session-1")
        ctx = cm.update_user_query("Check this code", visible_snippet="x = 10")

        assert ctx.user_query == "Check this code"
        assert ctx.active_window.visible_snippet == "x = 10"

    def test_update_active_window(self):
        """Verify active window updates."""
        cm = ContextManager("session-1")
        win = cm.update_active_window(
            app_name="Terminal",
            window_title="bash - SDK-9",
            app_type="terminal",
            visible_snippet="pytest passed",
        )
        assert win.app_name == "Terminal"
        assert win.app_type == "terminal"
        assert cm.get_context().active_window.app_name == "Terminal"

    def test_add_turn_validations(self):
        """Verify role and content validation when adding turns."""
        cm = ContextManager("session-1")

        with pytest.raises(ValueError, match="Invalid role 'invalid_role'"):
            cm.add_turn(role="invalid_role", content="text")  # type: ignore

        with pytest.raises(ValueError, match="Turn content cannot be empty"):
            cm.add_turn(role="user", content="")

    def test_sliding_window_history(self):
        """Verify max_turns bounds prevent memory leaks."""
        cm = ContextManager("session-1", max_turns=3)
        cm.add_turn("user", "Msg 1")
        cm.add_turn("assistant", "Msg 2")
        cm.add_turn("user", "Msg 3")
        assert len(cm.get_context().history) == 3

        # Exceed max_turns
        cm.add_turn("assistant", "Msg 4")
        history = cm.get_context().history
        assert len(history) == 3
        assert history[0].content == "Msg 2"
        assert history[1].content == "Msg 3"
        assert history[2].content == "Msg 4"

    def test_get_history_summary(self):
        """Verify formatted dialogue generation."""
        cm = ContextManager("session-1")
        cm.add_turn("user", "What is the error?")
        cm.add_turn("assistant", "It is an IndexError.")

        summary = cm.get_history_summary()
        assert "User: What is the error?" in summary
        assert "Assistant: It is an IndexError." in summary

        # Test with max_turns subset
        summary_subset = cm.get_history_summary(max_turns=1)
        assert "User: What is the error?" not in summary_subset
        assert "Assistant: It is an IndexError." in summary_subset

    def test_clear_and_reset(self):
        """Verify clear_history and reset."""
        cm = ContextManager("session-1")
        cm.add_turn("user", "Hello")
        cm.update_user_query("Check this")

        cm.clear_history()
        assert len(cm.get_context().history) == 0
        assert cm.get_context().user_query == "Check this"

        cm.reset()
        assert cm.get_context().user_query == ""
        assert len(cm.get_context().history) == 0
        assert cm.get_context().session_id == "session-1"

    def test_serialization_roundtrip_dict(self):
        """Verify state serialization and restoration via dictionary."""
        cm = ContextManager("session-roundtrip", max_turns=50)
        cm.update_active_window("VS Code", "main.py", visible_snippet="print(1)")
        cm.add_turn("user", "Explain line 1")
        cm.add_turn("assistant", "It prints 1.")
        cm.update_user_query("Thanks!")

        serialized = cm.to_dict()
        assert isinstance(serialized, dict)
        assert serialized["session_id"] == "session-roundtrip"

        restored_cm = ContextManager.from_dict(serialized, max_turns=50)
        restored_ctx = restored_cm.get_context()
        assert restored_ctx.session_id == "session-roundtrip"
        assert restored_ctx.user_query == "Thanks!"
        assert len(restored_ctx.history) == 2
        assert restored_ctx.active_window.visible_snippet == "print(1)"

    def test_serialization_roundtrip_json(self):
        """Verify state serialization and restoration via JSON string."""
        cm = ContextManager("session-json", max_turns=20)
        cm.add_turn("user", "Run tests")
        cm.update_user_query("pytest")

        json_str = cm.to_json(indent=2)
        assert isinstance(json_str, str)
        assert "session-json" in json_str

        restored_cm = ContextManager.from_json(json_str)
        assert restored_cm.session_id == "session-json"
        assert restored_cm.get_context().user_query == "pytest"

    def test_immutability_of_get_context(self):
        """Verify get_context returns a copy preventing external mutation."""
        cm = ContextManager("session-immutable")
        cm.add_turn("user", "Original")
        ctx = cm.get_context()
        ctx.history.clear()

        # Internal state should remain intact
        assert len(cm.get_context().history) == 1


# =============================================================================
# 3. Versioned Prompt Manager Tests
# =============================================================================

class TestVersionedPromptManager:
    """Tests for VersionedPromptManager templates and rendering."""

    def test_builtin_templates_loaded(self):
        """Verify v1.0, v1.1, and v2.0 built-in templates are present."""
        pm = VersionedPromptManager()
        versions = pm.list_versions()
        assert "v1.0" in versions
        assert "v1.1" in versions
        assert "v2.0" in versions
        assert pm.default_version == "v1.0"

    def test_custom_template_registration(self):
        """Verify custom template registration and auto variable detection."""
        pm = VersionedPromptManager()
        template = pm.register_template(
            version="v2.5-custom",
            template="Agent in {app_name} received {query} with data {custom_var}.",
            description="Custom test template",
        )
        assert template.version == "v2.5-custom"
        assert set(template.variables) == {"app_name", "query", "custom_var"}

        rendered = pm.render_prompt(
            version="v2.5-custom",
            app_name="Sublime Text",
            query="Analyze file",
            custom_var="custom_123",
        )
        assert "Agent in Sublime Text received Analyze file with data custom_123." == rendered

    def test_registration_validation(self):
        """Verify empty version or template raises ValueError."""
        pm = VersionedPromptManager()
        with pytest.raises(ValueError, match="Template version cannot be empty"):
            pm.register_template("", "template")
        with pytest.raises(ValueError, match="Template content cannot be empty"):
            pm.register_template("v1", "")

    def test_render_with_missing_placeholders(self):
        """Verify graceful fallback when variable is not provided."""
        pm = VersionedPromptManager()
        pm.register_template("v-missing", "Value: {missing_key}")
        rendered = pm.render_prompt("v-missing")
        assert "Value: [missing_key: not provided]" == rendered

    def test_unknown_version_errors(self):
        """Verify KeyError on unknown version request or default set."""
        pm = VersionedPromptManager()
        with pytest.raises(KeyError, match="Prompt template version 'v999' not found"):
            pm.get_template("v999")

        with pytest.raises(KeyError, match="Cannot set unknown version 'v999' as default"):
            pm.set_default_version("v999")

    def test_set_default_version(self):
        """Verify default version switching."""
        pm = VersionedPromptManager()
        pm.set_default_version("v1.1")
        assert pm.default_version == "v1.1"
        assert pm.get_template().version == "v1.1"


# =============================================================================
# 4. Mock Reasoning Service Tests
# =============================================================================

class TestMockReasoningService:
    """Tests for MockReasoningService intent classification and rule dispatch."""

    def setup_method(self):
        self.reasoner = MockReasoningService()
        self.cm = ContextManager("test-session")

    def test_empty_query_idle(self):
        """Verify idle response on empty query."""
        ctx = self.cm.get_context()
        result = self.reasoner.reason(ctx)
        assert result.intent == "IDLE"
        assert result.requires_tool is False
        assert result.confidence == 0.99
        assert "listening" in result.direct_response.lower()

    def test_explain_error_intent(self):
        """Verify error diagnostic intent and specific exception matching."""
        # Test IndexError
        self.cm.update_active_window("VS Code", "app.py", visible_snippet="items = []\nitem = items[0]  # IndexError")
        self.cm.update_user_query("Why did this IndexError happen?")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "EXPLAIN_ERROR"
        assert res.requires_tool is False
        assert "IndexError" in res.direct_response
        assert res.confidence >= 0.95
        assert len(res.reasoning_steps) > 0

        # Test KeyError
        self.cm.update_active_window("VS Code", "app.py", visible_snippet="d = {}\nx = d['missing_key']  # KeyError")
        self.cm.update_user_query("Got a KeyError")
        res_key = self.reasoner.reason(self.cm.get_context())
        assert "KeyError" in res_key.direct_response

        # Test TypeError
        self.cm.update_active_window("VS Code", "app.py", visible_snippet="a = '1' + 2  # TypeError")
        self.cm.update_user_query("Got a TypeError")
        res_type = self.reasoner.reason(self.cm.get_context())
        assert "TypeError" in res_type.direct_response

        # Test general snippet error
        self.cm.update_active_window("VS Code", "app.py", visible_snippet="assert False")
        self.cm.update_user_query("Why did it fail?")
        res_gen = self.reasoner.reason(self.cm.get_context())
        assert "active snippet contains an issue" in res_gen.direct_response

        # Test error without snippet
        self.cm.update_active_window("VS Code", "app.py", visible_snippet=None)
        self.cm.update_user_query("There is a crash here")
        res_nosnip = self.reasoner.reason(self.cm.get_context())
        assert "traceback logs" in res_nosnip.direct_response

    def test_code_summary_empty_snippet(self):
        """Verify code summary message when snippet is empty."""
        self.cm.update_active_window("VS Code", "empty.py", visible_snippet="")
        self.cm.update_user_query("Summarize this code")
        res = self.reasoner.reason(self.cm.get_context())
        assert "no visible code snippet selected" in res.direct_response

    def test_search_and_move_fallbacks(self):
        """Verify fallback pattern and paths when regex does not match."""
        # Unstructured search query
        self.cm.update_user_query("search file")
        res_search = self.reasoner.reason(self.cm.get_context())
        assert res_search.tool_parameters["pattern"] == "file"

        # Search with no tokens fallback
        pattern = self.reasoner._extract_search_pattern("")
        assert pattern == "*.py"

        # Move without 'to'
        paths = self.reasoner._extract_move_paths("move file")
        assert paths == ("source.txt", "destination.txt")

        # Math without digits
        expr = self.reasoner._extract_math_expression("calculate")
        assert expr == "0"

    def test_file_search_intent(self):
        """Verify file search tool triggering and pattern extraction."""
        self.cm.update_user_query("Search for *.json files in the repository")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "FILE_SEARCH"
        assert res.requires_tool is True
        assert res.planned_tool_name == "file.search"
        assert "*.json" in res.tool_parameters["pattern"]

    def test_file_move_intent(self):
        """Verify file move tool triggering and source/destination extraction."""
        self.cm.update_user_query("Move old_config.json to new_config.json")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "FILE_MOVE"
        assert res.requires_tool is True
        assert res.planned_tool_name == "file.move"
        assert res.tool_parameters["source"] == "old_config.json"
        assert res.tool_parameters["destination"] == "new_config.json"

    def test_calculate_intent(self):
        """Verify mathematical expression calculation intent."""
        self.cm.update_user_query("Calculate 25 * 4 + 10")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "CALCULATE"
        assert res.requires_tool is True
        assert res.planned_tool_name == "calc.evaluate"
        assert "25 * 4 + 10" in res.tool_parameters["expression"]

    def test_summarize_code_intent(self):
        """Verify code summarization using editor snippet."""
        code = "def process():\n    x = 1\n    return x"
        self.cm.update_active_window("VS Code", "worker.py", visible_snippet=code)
        self.cm.update_user_query("Summarize this code for me")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "SUMMARIZE_CODE"
        assert res.requires_tool is False
        assert "spans 3 lines" in res.direct_response

    def test_general_conversation_intent(self):
        """Verify greetings and general assistance queries."""
        self.cm.update_user_query("Hello! Who are you?")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "GENERAL_CONVERSATION"
        assert res.requires_tool is False
        assert "AI Voice Co-Pilot" in res.direct_response

    def test_fallback_conversation_intent(self):
        """Verify fallback response for unclassified queries."""
        self.cm.update_user_query("Let's look into the architecture")
        res = self.reasoner.reason(self.cm.get_context())

        assert res.intent == "DEFAULT_CONVERSATION"
        assert res.requires_tool is False
        assert res.confidence == 0.85


# =============================================================================
# 5. Full Pipeline Integration Tests
# =============================================================================

class TestPipelineIntegration:
    """Tests the interaction between ContextManager, PromptManager, and MockReasoningService."""

    def test_end_to_end_reasoning_and_prompt_pipeline(self):
        """Simulate a multi-turn developer interaction."""
        session_id = "test-e2e-session"
        cm = ContextManager(session_id=session_id)
        pm = VersionedPromptManager()
        reasoner = MockReasoningService()

        # Turn 1: User asks for file search
        cm.update_active_window("VS Code", "index.ts", app_type="ide", visible_snippet="import express from 'express';")
        query1 = "Search for models.py in the packages folder"
        cm.add_turn("user", query1)
        ctx1 = cm.update_user_query(query1)

        decision1 = reasoner.reason(ctx1)
        assert decision1.intent == "FILE_SEARCH"
        assert decision1.requires_tool is True
        cm.add_turn("assistant", decision1.direct_response or "")

        # Turn 2: User asks follow-up calculation
        query2 = "What is 1024 * 768?"
        cm.add_turn("user", query2)
        ctx2 = cm.update_user_query(query2)

        decision2 = reasoner.reason(ctx2)
        assert decision2.intent == "CALCULATE"
        cm.add_turn("assistant", decision2.direct_response or "")

        # Verify history accumulation
        assert len(cm.get_context().history) == 4

        # Render prompt for turn 2
        rendered = pm.render_prompt(
            version="v1.0",
            app_name=ctx2.active_window.app_name,
            snippet=ctx2.active_window.visible_snippet or "",
            query=ctx2.user_query,
            history=cm.get_history_summary(),
        )
        assert "Search for models.py" in rendered
        assert "What is 1024 * 768?" in rendered


# =============================================================================
# 6. CLI Simulation Test
# =============================================================================

class TestCLISimulation:
    """Verifies that the CLI simulation and interactive repl run without errors."""

    def test_run_simulation_completes_cleanly(self, capsys):
        """Verify that run_simulation() executes without throwing exceptions."""
        run_simulation()
        captured = capsys.readouterr()
        assert "Simulation complete" in captured.out
        assert "SDK-9 AI Voice Co-Pilot" in captured.out

    def test_run_interactive_flow(self, monkeypatch, capsys):
        """Verify interactive REPL handles inputs, window updates, and exit cleanly."""
        from packages.context_reasoning.cli import run_interactive

        inputs = iter([
            "",                         # Empty line
            ":window Terminal",         # Window switch command
            "Search for test files",    # Tool query
            "quit",                     # Quit command
        ])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

        run_interactive()
        captured = capsys.readouterr()
        assert "SDK-9 Context & Reasoning Interactive REPL" in captured.out
        assert "Updated active app to: Terminal" in captured.out
        assert "FILE_SEARCH" in captured.out
        assert "Session ended." in captured.out

    def test_run_interactive_keyboard_interrupt(self, monkeypatch, capsys):
        """Verify interactive REPL exits gracefully on KeyboardInterrupt."""
        from packages.context_reasoning.cli import run_interactive

        monkeypatch.setattr("builtins.input", lambda prompt="": (_ for _ in ()).throw(KeyboardInterrupt))
        run_interactive()
        captured = capsys.readouterr()
        assert "Exiting." in captured.out

    def test_main_cli_entrypoint(self, monkeypatch):
        """Verify main() argument parsing."""
        from packages.context_reasoning.cli import main

        monkeypatch.setattr("sys.argv", ["cli.py", "--simulate"])
        main()

