from packages.agentic_workflow import (
    AgentStateMachine,
    MockToolExecutor,
    AgentState,
    SafetyLevel,
    WorkflowStep,
)


def test_state_machine_approval_gate():
    sm = AgentStateMachine()
    step_safe = WorkflowStep(
        id="s1",
        step_number=1,
        description="Search files",
        tool_name="file.search",
        safety_level=SafetyLevel.A,
    )
    plan_safe = sm.build_plan("sess-1", "Search for files", [step_safe])
    assert plan_safe.requires_approval is False
    assert sm.state == AgentState.EXECUTING

    step_sensitive = WorkflowStep(
        id="s2",
        step_number=2,
        description="Move project files",
        tool_name="file.move",
        parameters={"source": "/tmp/a.txt", "destination": "/dest/"},
        safety_level=SafetyLevel.C,
    )
    plan_sensitive = sm.build_plan("sess-2", "Move files", [step_sensitive])
    assert plan_sensitive.requires_approval is True
    assert plan_sensitive.overall_safety_level == SafetyLevel.C
    assert sm.state == AgentState.AWAITING_APPROVAL


def test_mock_tool_executor():
    executor = MockToolExecutor()

    res_search = executor.execute("file.search", {"query": "report"})
    assert res_search.success is True
    assert len(res_search.output["matches"]) > 0

    res_calc = executor.execute("calc.evaluate", {"expression": "6 * 7"})
    assert res_calc.success is True
    assert res_calc.output["result"] == 42
