"""
Comprehensive unit and integration tests for the Agentic Workflow module.

Coverage targets:
    * :mod:`packages.agentic_workflow.models` – all model fields and helpers.
    * :mod:`packages.agentic_workflow.state_machine` – every valid/invalid
      transition, safety gate, approval/rejection, error handling, and recovery.
    * :mod:`packages.agentic_workflow.mock_executor` – all registered tools,
      error paths, unknown tools, and simulated failure mode.

Run with::

    .venv/bin/pytest --cov=packages/agentic_workflow packages/agentic_workflow/tests/ -v
"""

from __future__ import annotations

import time
from typing import List

import pytest

from packages.agentic_workflow.mock_executor import MockToolExecutor, _safe_eval
from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    SafetyLevel,
    ToolResult,
    WorkflowStep,
    highest_safety_level,
)
from packages.agentic_workflow.state_machine import (
    AgentStateMachine,
    InvalidTransitionError,
    StateTransitionRecord,
)
import ast

# ===========================================================================
# Helpers
# ===========================================================================


def _make_step(
    tool_name: str = "file.search",
    safety_level: SafetyLevel = SafetyLevel.A,
    step_number: int = 1,
    description: str = "Test step",
    parameters: dict | None = None,
) -> WorkflowStep:
    """Factory helper for :class:`WorkflowStep` in tests."""
    return WorkflowStep(
        step_number=step_number,
        description=description,
        tool_name=tool_name,
        safety_level=safety_level,
        parameters=parameters or {},
    )


def _sm_in_planning() -> AgentStateMachine:
    """Return an :class:`AgentStateMachine` already in PLANNING state."""
    sm = AgentStateMachine()
    sm.transition_to(AgentState.LISTENING)
    sm.transition_to(AgentState.PLANNING)
    return sm


# ===========================================================================
# Model Tests
# ===========================================================================


class TestSafetyLevel:
    def test_enum_values(self):
        assert SafetyLevel.A == "A"
        assert SafetyLevel.B == "B"
        assert SafetyLevel.C == "C"
        assert SafetyLevel.D == "D"

    def test_highest_safety_level_single(self):
        assert highest_safety_level([SafetyLevel.A]) == SafetyLevel.A

    def test_highest_safety_level_mixed(self):
        assert highest_safety_level([SafetyLevel.A, SafetyLevel.C]) == SafetyLevel.C

    def test_highest_safety_level_all(self):
        levels = [SafetyLevel.B, SafetyLevel.D, SafetyLevel.A, SafetyLevel.C]
        assert highest_safety_level(levels) == SafetyLevel.D

    def test_highest_safety_level_empty_raises(self):
        with pytest.raises(ValueError):
            highest_safety_level([])


class TestAgentState:
    def test_all_states_exist(self):
        expected = {
            "IDLE", "LISTENING", "PLANNING", "AWAITING_APPROVAL",
            "EXECUTING", "VERIFYING", "RESPONDING", "ERROR",
        }
        assert {s.value for s in AgentState} == expected


class TestWorkflowStep:
    def test_defaults(self):
        step = _make_step()
        assert step.status == "pending"
        assert step.result is None
        assert step.error is None
        assert step.retry_count == 0
        assert step.started_at is None
        assert step.completed_at is None
        assert step.execution_logs == []
        assert len(step.id) > 0  # UUID assigned

    def test_custom_fields(self):
        step = WorkflowStep(
            id="custom-id",
            step_number=3,
            description="Move logs",
            tool_name="file.move",
            safety_level=SafetyLevel.D,
            parameters={"source": "/a", "destination": "/b"},
            status="running",
            retry_count=2,
        )
        assert step.id == "custom-id"
        assert step.retry_count == 2
        assert step.status == "running"

    def test_execution_logs_mutable(self):
        step = _make_step()
        step.execution_logs.append("started")
        assert len(step.execution_logs) == 1


class TestActionPlan:
    def test_defaults(self):
        plan = ActionPlan(session_id="s1", goal="do stuff")
        assert plan.requires_approval is False
        assert plan.steps == []
        assert plan.current_step_index == 0
        assert plan.approved_at is None
        assert plan.rejected_at is None
        assert plan.rejection_reason is None
        assert plan.execution_logs == []
        assert plan.overall_safety_level == SafetyLevel.A
        assert len(plan.plan_id) > 0

    def test_created_at_is_recent(self):
        before = time.time()
        plan = ActionPlan(session_id="s1", goal="do stuff")
        after = time.time()
        assert before <= plan.created_at <= after


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(tool_name="file.search", success=True, output=["a.py"], duration_ms=12.5)
        assert r.success is True
        assert r.error is None
        assert r.duration_ms == 12.5

    def test_failure_result(self):
        r = ToolResult(tool_name="file.move", success=False, output=None, duration_ms=2.0, error="oops")
        assert r.success is False
        assert r.error == "oops"
        assert r.output is None

    def test_timestamp_populated(self):
        before = time.time()
        r = ToolResult(tool_name="calc.evaluate", success=True, output=42, duration_ms=1.0)
        assert r.timestamp >= before


# ===========================================================================
# State Machine Transition Tests
# ===========================================================================


class TestStateMachineInit:
    def test_initial_state_is_idle(self):
        sm = AgentStateMachine()
        assert sm.state == AgentState.IDLE

    def test_initial_plan_is_none(self):
        sm = AgentStateMachine()
        assert sm.current_plan is None

    def test_initial_history_empty(self):
        sm = AgentStateMachine()
        assert sm.transition_history == []


class TestValidTransitions:
    """All valid edges in the FSM transition table."""

    @pytest.mark.parametrize("path", [
        [AgentState.LISTENING],
        [AgentState.LISTENING, AgentState.PLANNING],
        [AgentState.LISTENING, AgentState.PLANNING, AgentState.EXECUTING],
        [AgentState.LISTENING, AgentState.PLANNING, AgentState.AWAITING_APPROVAL],
        [AgentState.LISTENING, AgentState.IDLE],
        [AgentState.ERROR],
    ])
    def test_valid_path_from_idle(self, path: List[AgentState]):
        sm = AgentStateMachine()
        for state in path:
            sm.transition_to(state)
        assert sm.state == path[-1]

    def test_full_happy_path(self):
        sm = AgentStateMachine()
        path = [
            AgentState.LISTENING,
            AgentState.PLANNING,
            AgentState.EXECUTING,
            AgentState.VERIFYING,
            AgentState.RESPONDING,
            AgentState.IDLE,
        ]
        for state in path:
            sm.transition_to(state)
        assert sm.state == AgentState.IDLE

    def test_approval_path(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.AWAITING_APPROVAL)
        sm.transition_to(AgentState.EXECUTING)
        sm.transition_to(AgentState.VERIFYING)
        sm.transition_to(AgentState.RESPONDING)
        sm.transition_to(AgentState.IDLE)
        assert sm.state == AgentState.IDLE

    def test_error_from_executing(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.EXECUTING)
        sm.transition_to(AgentState.ERROR)
        assert sm.state == AgentState.ERROR

    def test_recovery_error_to_idle(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.ERROR)
        sm.transition_to(AgentState.IDLE)
        assert sm.state == AgentState.IDLE


class TestInvalidTransitions:
    """Guards against edges absent from the FSM transition table."""

    @pytest.mark.parametrize("from_state,to_state", [
        (AgentState.IDLE, AgentState.PLANNING),
        (AgentState.IDLE, AgentState.EXECUTING),
        (AgentState.IDLE, AgentState.AWAITING_APPROVAL),
        (AgentState.LISTENING, AgentState.EXECUTING),
        (AgentState.LISTENING, AgentState.AWAITING_APPROVAL),
        (AgentState.PLANNING, AgentState.IDLE),
        (AgentState.PLANNING, AgentState.RESPONDING),
        (AgentState.AWAITING_APPROVAL, AgentState.PLANNING),
        (AgentState.AWAITING_APPROVAL, AgentState.VERIFYING),
        (AgentState.EXECUTING, AgentState.IDLE),
        (AgentState.EXECUTING, AgentState.PLANNING),
        (AgentState.VERIFYING, AgentState.IDLE),
        (AgentState.RESPONDING, AgentState.PLANNING),
        (AgentState.ERROR, AgentState.PLANNING),
        (AgentState.ERROR, AgentState.EXECUTING),
    ])
    def test_invalid_transition_raises(self, from_state: AgentState, to_state: AgentState):
        sm = AgentStateMachine()
        # Navigate to from_state
        _navigate_to(sm, from_state)
        with pytest.raises(InvalidTransitionError):
            sm.transition_to(to_state)


def _navigate_to(sm: AgentStateMachine, target: AgentState) -> None:
    """Drive the FSM to the target state via a known valid path."""
    paths: dict[AgentState, list[AgentState]] = {
        AgentState.IDLE: [],
        AgentState.LISTENING: [AgentState.LISTENING],
        AgentState.PLANNING: [AgentState.LISTENING, AgentState.PLANNING],
        AgentState.AWAITING_APPROVAL: [
            AgentState.LISTENING, AgentState.PLANNING, AgentState.AWAITING_APPROVAL
        ],
        AgentState.EXECUTING: [
            AgentState.LISTENING, AgentState.PLANNING, AgentState.EXECUTING
        ],
        AgentState.VERIFYING: [
            AgentState.LISTENING, AgentState.PLANNING, AgentState.EXECUTING, AgentState.VERIFYING
        ],
        AgentState.RESPONDING: [
            AgentState.LISTENING, AgentState.PLANNING, AgentState.EXECUTING,
            AgentState.VERIFYING, AgentState.RESPONDING,
        ],
        AgentState.ERROR: [AgentState.ERROR],
    }
    for state in paths[target]:
        sm.transition_to(state)


class TestCanTransitionTo:
    def test_returns_true_for_valid(self):
        sm = AgentStateMachine()
        assert sm.can_transition_to(AgentState.LISTENING) is True

    def test_returns_false_for_invalid(self):
        sm = AgentStateMachine()
        assert sm.can_transition_to(AgentState.PLANNING) is False

    def test_returns_false_after_state_change(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        assert sm.can_transition_to(AgentState.IDLE) is True
        assert sm.can_transition_to(AgentState.EXECUTING) is False


class TestTransitionHistory:
    def test_history_recorded(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        assert len(sm.transition_history) == 2

    def test_history_content(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        record = sm.transition_history[0]
        assert isinstance(record, StateTransitionRecord)
        assert record.from_state == AgentState.IDLE
        assert record.to_state == AgentState.LISTENING
        assert record.timestamp > 0

    def test_get_transition_history_tuples(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        history = sm.get_transition_history()
        assert history[0] == ("IDLE", "LISTENING", history[0][2])

    def test_metadata_stored(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING, metadata={"source": "voice"})
        assert sm.transition_history[0].metadata["source"] == "voice"


# ===========================================================================
# Safety Gate (build_plan) Tests
# ===========================================================================


class TestBuildPlanSafetyGate:
    def test_level_a_auto_proceeds_to_executing(self):
        sm = _sm_in_planning()
        steps = [_make_step(safety_level=SafetyLevel.A)]
        plan = sm.build_plan("s1", "Search logs", steps)
        assert sm.state == AgentState.EXECUTING
        assert plan.requires_approval is False
        assert plan.overall_safety_level == SafetyLevel.A

    def test_level_b_auto_proceeds_to_executing(self):
        sm = _sm_in_planning()
        steps = [_make_step(safety_level=SafetyLevel.B)]
        plan = sm.build_plan("s1", "Notify user", steps)
        assert sm.state == AgentState.EXECUTING
        assert plan.requires_approval is False
        assert plan.overall_safety_level == SafetyLevel.B

    def test_mixed_ab_auto_proceeds_to_executing(self):
        sm = _sm_in_planning()
        steps = [
            _make_step(safety_level=SafetyLevel.A, step_number=1),
            _make_step(safety_level=SafetyLevel.B, step_number=2),
        ]
        plan = sm.build_plan("s1", "Search and notify", steps)
        assert sm.state == AgentState.EXECUTING
        assert plan.requires_approval is False
        assert plan.overall_safety_level == SafetyLevel.B

    def test_level_c_requires_approval(self):
        sm = _sm_in_planning()
        steps = [_make_step(safety_level=SafetyLevel.C)]
        plan = sm.build_plan("s1", "Edit config", steps)
        assert sm.state == AgentState.AWAITING_APPROVAL
        assert plan.requires_approval is True
        assert plan.overall_safety_level == SafetyLevel.C

    def test_level_d_requires_approval(self):
        sm = _sm_in_planning()
        steps = [_make_step(safety_level=SafetyLevel.D)]
        plan = sm.build_plan("s1", "Delete files", steps)
        assert sm.state == AgentState.AWAITING_APPROVAL
        assert plan.requires_approval is True
        assert plan.overall_safety_level == SafetyLevel.D

    def test_mixed_abcd_requires_approval(self):
        sm = _sm_in_planning()
        steps = [
            _make_step(safety_level=SafetyLevel.A, step_number=1),
            _make_step(safety_level=SafetyLevel.C, step_number=2),
        ]
        plan = sm.build_plan("s1", "Mixed plan", steps)
        assert sm.state == AgentState.AWAITING_APPROVAL
        assert plan.requires_approval is True
        assert plan.overall_safety_level == SafetyLevel.C

    def test_highest_level_wins_when_d_present(self):
        sm = _sm_in_planning()
        steps = [
            _make_step(safety_level=SafetyLevel.C, step_number=1),
            _make_step(safety_level=SafetyLevel.D, step_number=2),
        ]
        plan = sm.build_plan("s1", "Destroy everything", steps)
        assert plan.overall_safety_level == SafetyLevel.D

    def test_plan_stored_on_state_machine(self):
        sm = _sm_in_planning()
        steps = [_make_step(safety_level=SafetyLevel.A)]
        plan = sm.build_plan("s1", "goal", steps)
        assert sm.current_plan is plan

    def test_build_plan_requires_planning_state(self):
        sm = AgentStateMachine()
        steps = [_make_step()]
        with pytest.raises(InvalidTransitionError):
            sm.build_plan("s1", "goal", steps)

    def test_build_plan_sets_session_and_goal(self):
        sm = _sm_in_planning()
        steps = [_make_step()]
        plan = sm.build_plan("my-session", "My goal", steps)
        assert plan.session_id == "my-session"
        assert plan.goal == "My goal"

    def test_build_plan_with_empty_steps(self):
        """Empty step list should default to SafetyLevel A and proceed to EXECUTING."""
        sm = _sm_in_planning()
        plan = sm.build_plan("s1", "empty plan", [])
        assert plan.requires_approval is False
        assert sm.state == AgentState.EXECUTING


# ===========================================================================
# Approval / Rejection Tests
# ===========================================================================


class TestApprovePlan:
    def test_approve_transitions_to_executing(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Delete files", [_make_step(safety_level=SafetyLevel.D)])
        plan = sm.approve_plan()
        assert sm.state == AgentState.EXECUTING
        assert plan.approved_at is not None

    def test_approve_sets_timestamp(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Sensitive", [_make_step(safety_level=SafetyLevel.C)])
        before = time.time()
        sm.approve_plan()
        assert sm.current_plan.approved_at >= before

    def test_approve_adds_log_entry(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Sensitive", [_make_step(safety_level=SafetyLevel.C)])
        sm.approve_plan()
        assert any("approved" in log.lower() for log in sm.current_plan.execution_logs)

    def test_approve_fails_if_not_awaiting(self):
        sm = AgentStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.approve_plan()

    def test_approve_fails_with_no_plan(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.AWAITING_APPROVAL)
        with pytest.raises(RuntimeError):
            sm.approve_plan()


class TestRejectPlan:
    def test_reject_transitions_to_idle(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Delete files", [_make_step(safety_level=SafetyLevel.D)])
        sm.reject_plan("Too risky")
        assert sm.state == AgentState.IDLE

    def test_reject_sets_timestamps_and_reason(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Delete", [_make_step(safety_level=SafetyLevel.C)])
        before = time.time()
        rejected = sm.reject_plan("Not now")
        assert rejected.rejected_at >= before
        assert rejected.rejection_reason == "Not now"

    def test_reject_marks_steps_as_rejected(self):
        sm = _sm_in_planning()
        steps = [
            _make_step(safety_level=SafetyLevel.C, step_number=1),
            _make_step(safety_level=SafetyLevel.C, step_number=2),
        ]
        sm.build_plan("s1", "Multi step", steps)
        rejected = sm.reject_plan("Denied")
        assert all(s.status == "rejected" for s in rejected.steps)

    def test_reject_clears_current_plan(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "Delete", [_make_step(safety_level=SafetyLevel.C)])
        sm.reject_plan("No")
        assert sm.current_plan is None

    def test_reject_fails_if_not_awaiting(self):
        sm = AgentStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.reject_plan("reason")

    def test_reject_fails_with_no_plan(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        sm.transition_to(AgentState.AWAITING_APPROVAL)
        with pytest.raises(RuntimeError):
            sm.reject_plan("reason")


# ===========================================================================
# Error Handling & Recovery Tests
# ===========================================================================


class TestErrorHandling:
    def test_handle_error_transitions_to_error(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.handle_error("Something went wrong")
        assert sm.state == AgentState.ERROR

    def test_handle_error_from_executing(self):
        sm = _sm_in_planning()
        sm.build_plan("s1", "goal", [_make_step()])
        sm.handle_error("Tool failed")
        assert sm.state == AgentState.ERROR

    def test_handle_error_returns_metadata(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        before = time.time()
        meta = sm.handle_error("Network error")
        assert meta["error_message"] == "Network error"
        assert meta["previous_state"] == "LISTENING"
        assert meta["timestamp"] >= before

    def test_handle_error_stores_plan_id(self):
        sm = _sm_in_planning()
        plan = sm.build_plan("s1", "goal", [_make_step()])
        meta = sm.handle_error("Oops")
        assert meta["plan_id"] == plan.plan_id

    def test_handle_error_stores_none_plan_id_when_no_plan(self):
        sm = AgentStateMachine()
        meta = sm.handle_error("Boot failure")
        assert meta["plan_id"] is None

    def test_error_context_stored(self):
        sm = AgentStateMachine()
        sm.handle_error("crash")
        assert sm.error_context is not None
        assert sm.error_context["error_message"] == "crash"

    def test_reset_from_error(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.ERROR)
        sm.reset()
        assert sm.state == AgentState.IDLE
        assert sm.current_plan is None
        assert sm.error_context is None

    def test_reset_fails_if_not_in_error(self):
        sm = AgentStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.reset()

    def test_full_error_recovery_cycle(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.handle_error("crash")
        assert sm.state == AgentState.ERROR
        sm.reset()
        assert sm.state == AgentState.IDLE
        # Should be able to restart
        sm.transition_to(AgentState.LISTENING)
        assert sm.state == AgentState.LISTENING


# ===========================================================================
# MockToolExecutor Tests
# ===========================================================================


class TestFileSearch:
    def test_returns_success(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.py", "directory": "/src"})
        assert result.success is True
        assert result.tool_name == "file.search"
        assert result.error is None

    def test_returns_list_of_matches(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.py", "directory": "/src"})
        assert isinstance(result.output["matches"], list)
        assert len(result.output["matches"]) > 0

    def test_paths_contain_directory(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.py", "directory": "/src"})
        for path in result.output["matches"]:
            assert path.startswith("/src/")

    def test_pattern_and_directory_echoed(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.txt", "directory": "/logs"})
        assert result.output["pattern"] == "*.txt"
        assert result.output["directory"] == "/logs"

    def test_max_results_respected(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.log", "directory": "/var", "max_results": 2})
        assert result.output["total_found"] <= 2
        assert len(result.output["matches"]) <= 2

    def test_default_parameters(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {})
        assert result.success is True

    def test_duration_ms_non_negative(self):
        ex = MockToolExecutor()
        result = ex.execute("file.search", {"pattern": "*.py"})
        assert result.duration_ms >= 0


class TestFileMove:
    def test_valid_move_returns_success(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"source": "/tmp/a.txt", "destination": "/home/b.txt"})
        assert result.success is True
        assert result.output["status"] == "moved"
        assert result.output["source"] == "/tmp/a.txt"
        assert result.output["destination"] == "/home/b.txt"

    def test_move_with_overwrite_flag(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {
            "source": "/a/file.txt",
            "destination": "/b/file.txt",
            "overwrite": True,
        })
        assert result.output["overwrite"] is True

    def test_missing_source_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"destination": "/b.txt"})
        assert result.success is False
        assert "source" in result.error.lower()

    def test_missing_destination_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"source": "/a.txt"})
        assert result.success is False
        assert "destination" in result.error.lower()

    def test_empty_source_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"source": "", "destination": "/b.txt"})
        assert result.success is False

    def test_empty_destination_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"source": "/a.txt", "destination": ""})
        assert result.success is False

    def test_duration_ms_non_negative(self):
        ex = MockToolExecutor()
        result = ex.execute("file.move", {"source": "/a.txt", "destination": "/b.txt"})
        assert result.duration_ms >= 0


class TestCalcEvaluate:
    @pytest.mark.parametrize("expression,expected", [
        ("2 + 3", 5.0),
        ("10 - 4", 6.0),
        ("3 * 4", 12.0),
        ("10 / 4", 2.5),
        ("2 ** 3", 8.0),
        ("10 % 3", 1.0),
        ("10 // 3", 3.0),
        ("-5 + 10", 5.0),
        ("(2 + 3) * 4", 20.0),
    ])
    def test_valid_expressions(self, expression: str, expected: float):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": expression})
        assert result.success is True
        assert result.output["result"] == pytest.approx(expected)
        assert result.output["expression"] == expression

    def test_empty_expression_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": ""})
        assert result.success is False
        assert "expression" in result.error.lower()

    def test_missing_expression_key_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {})
        assert result.success is False

    def test_invalid_syntax_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": "2 +"})
        assert result.success is False

    def test_unsupported_function_call_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": "abs(-5)"})
        assert result.success is False

    def test_string_literal_returns_error(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": "'hello'"})
        assert result.success is False

    def test_duration_ms_non_negative(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": "1 + 1"})
        assert result.duration_ms >= 0


class TestUnknownTool:
    def test_unknown_tool_returns_failure(self):
        ex = MockToolExecutor()
        result = ex.execute("banana.peel", {})
        assert result.success is False
        assert "banana.peel" in result.error
        assert result.tool_name == "banana.peel"

    def test_unknown_tool_error_mentions_registered_tools(self):
        ex = MockToolExecutor()
        result = ex.execute("nonexistent.tool", {})
        # Error should hint at what's available
        assert "file.search" in result.error or "registered" in result.error.lower()

    def test_unknown_tool_duration_recorded(self):
        ex = MockToolExecutor()
        result = ex.execute("fake.tool", {})
        assert result.duration_ms >= 0


class TestSimulateFailureMode:
    def test_simulate_failure_flag(self):
        ex = MockToolExecutor(simulate_failure=True)
        result = ex.execute("file.search", {"pattern": "*.py"})
        assert result.success is False
        assert "simulated" in result.error.lower()

    def test_simulate_failure_on_all_tools(self):
        ex = MockToolExecutor(simulate_failure=True)
        for tool in ("file.search", "file.move", "calc.evaluate"):
            result = ex.execute(tool, {"expression": "1", "source": "/a", "destination": "/b", "pattern": "*"})
            assert result.success is False

    def test_simulate_failure_returns_tool_name(self):
        ex = MockToolExecutor(simulate_failure=True)
        result = ex.execute("file.move", {"source": "/a", "destination": "/b"})
        assert result.tool_name == "file.move"

    def test_simulate_failure_output_is_none(self):
        ex = MockToolExecutor(simulate_failure=True)
        result = ex.execute("calc.evaluate", {"expression": "1 + 1"})
        assert result.output is None

    def test_no_failure_by_default(self):
        ex = MockToolExecutor()
        result = ex.execute("calc.evaluate", {"expression": "1 + 1"})
        assert result.success is True


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestIntegrationWorkflow:
    """End-to-end scenarios combining state machine and tool executor."""

    def test_safe_plan_executes_tool_and_completes(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        steps = [
            _make_step(
                tool_name="file.search",
                safety_level=SafetyLevel.A,
                parameters={"pattern": "*.log", "directory": "/var/logs"},
            )
        ]
        plan = sm.build_plan("session-42", "Find log files", steps)
        assert sm.state == AgentState.EXECUTING

        executor = MockToolExecutor()
        for step in plan.steps:
            result = executor.execute(step.tool_name, step.parameters)
            step.status = "completed" if result.success else "failed"
            step.result = result.output
        
        sm.transition_to(AgentState.VERIFYING)
        sm.transition_to(AgentState.RESPONDING)
        sm.transition_to(AgentState.IDLE)

        assert sm.state == AgentState.IDLE
        assert all(s.status == "completed" for s in plan.steps)

    def test_sensitive_plan_approval_then_execute(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        plan = sm.build_plan(
            "session-99",
            "Delete old logs",
            [_make_step(tool_name="file.move", safety_level=SafetyLevel.D,
                        parameters={"source": "/logs/old.log", "destination": "/archive/old.log"})],
        )
        assert sm.state == AgentState.AWAITING_APPROVAL

        sm.approve_plan()
        assert sm.state == AgentState.EXECUTING

        executor = MockToolExecutor()
        for step in plan.steps:
            result = executor.execute(step.tool_name, step.parameters)
            assert result.success is True
            step.status = "completed"

        sm.transition_to(AgentState.VERIFYING)
        sm.transition_to(AgentState.RESPONDING)
        sm.transition_to(AgentState.IDLE)
        assert sm.state == AgentState.IDLE

    def test_rejection_ends_workflow(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        sm.build_plan(
            "session-7",
            "Wipe database",
            [_make_step(safety_level=SafetyLevel.D)],
        )
        rejected = sm.reject_plan("Security policy violation")
        assert sm.state == AgentState.IDLE
        assert rejected.rejection_reason == "Security policy violation"

    def test_tool_failure_triggers_error_and_recovery(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        plan = sm.build_plan("session-5", "Move files", [
            _make_step(tool_name="file.move", safety_level=SafetyLevel.B,
                       parameters={"source": "/a.txt", "destination": "/b.txt"})
        ])
        assert sm.state == AgentState.EXECUTING

        executor = MockToolExecutor(simulate_failure=True)
        result = executor.execute("file.move", plan.steps[0].parameters)
        assert result.success is False

        sm.handle_error(result.error)
        assert sm.state == AgentState.ERROR

        sm.reset()
        assert sm.state == AgentState.IDLE

    def test_calc_in_plan(self):
        sm = _sm_in_planning()
        plan = sm.build_plan(
            "math-session",
            "Compute price",
            [_make_step(tool_name="calc.evaluate", safety_level=SafetyLevel.A,
                        parameters={"expression": "100 * 0.85"})],
        )
        executor = MockToolExecutor()
        result = executor.execute(plan.steps[0].tool_name, plan.steps[0].parameters)
        assert result.success is True
        assert result.output["result"] == pytest.approx(85.0)


# ===========================================================================
# _safe_eval unit tests (internal helper)
# ===========================================================================


class TestSafeEval:
    def test_integer_constant(self):
        node = ast.parse("42", mode="eval").body
        assert _safe_eval(node) == 42.0

    def test_float_constant(self):
        node = ast.parse("3.14", mode="eval").body
        assert _safe_eval(node) == pytest.approx(3.14)

    def test_unsupported_constant_raises(self):
        # String constant
        node = ast.parse("'hello'", mode="eval").body
        with pytest.raises(ValueError):
            _safe_eval(node)

    def test_unsupported_node_raises(self):
        # Name node (variable) is not supported
        node = ast.parse("x", mode="eval").body
        with pytest.raises(ValueError):
            _safe_eval(node)
