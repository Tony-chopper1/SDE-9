from packages.context_reasoning import (
    ContextManager,
    VersionedPromptManager,
    MockReasoningService,
)


def test_context_manager_updates():
    cm = ContextManager("session-123")
    ctx = cm.update_user_query("What does this error mean?", "Traceback...")

    assert ctx.user_query == "What does this error mean?"
    assert ctx.active_window.visible_snippet == "Traceback..."


def test_versioned_prompt_render():
    pm = VersionedPromptManager()
    rendered = pm.render_prompt(
        "v1.0",
        app_name="VS Code",
        snippet="NameError",
        query="Fix this error",
    )
    assert "VS Code" in rendered
    assert "NameError" in rendered


def test_mock_reasoning_intent_classification():
    cm = ContextManager("session-123")
    service = MockReasoningService()

    ctx = cm.update_user_query("Why is my code failing?")
    result = service.reason(ctx)
    assert result.intent == "EXPLAIN_ERROR"
    assert result.requires_tool is False
    assert result.direct_response is not None

    ctx2 = cm.update_user_query("Find my report document")
    result2 = service.reason(ctx2)
    assert result2.intent == "FILE_SEARCH"
    assert result2.requires_tool is True
    assert result2.planned_tool_name == "file.search"
