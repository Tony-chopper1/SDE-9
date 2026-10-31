"""
Unit Tests for Agentic Workflow Module
Assigned Member: Chiranthan Rk (feature/agentic-workflow - Task W4)

TODO (Chiranthan Rk):
Write unit tests for AgentStateMachine and MockToolExecutor to achieve >80% coverage.
"""
import pytest
from packages.agentic_workflow import SafetyLevel, AgentState, WorkflowStep, ActionPlan


def test_workflow_models_instantiation():
    """Verify that WorkflowStep and ActionPlan can be constructed."""
    step = WorkflowStep(
        id="step-1",
        step_number=1,
        description="Search files",
        tool_name="file.search",
        safety_level=SafetyLevel.A,
    )
    assert step.tool_name == "file.search"
    assert step.safety_level == SafetyLevel.A


# TODO (Chiranthan Rk): Uncomment and implement after completing state_machine.py and mock_executor.py
# def test_state_machine_approval_gate():
#     sm = AgentStateMachine()
#     ...
