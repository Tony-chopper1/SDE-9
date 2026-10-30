"""
Agent State Machine - Starter Template
Assigned Member: Chiranthan Rk (feature/agentic-workflow - Task W4)
"""
from typing import List
from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    SafetyLevel,
    WorkflowStep,
)


class AgentStateMachine:
    """
    Finite state machine managing multi-step agent decisions, transitions, and safety gate.
    
    TODO (Chiranthan Rk):
    1. Manage state transitions (IDLE -> LISTENING -> PLANNING -> AWAITING_APPROVAL -> EXECUTING -> RESPONDING).
    2. In build_plan:
       - Check if any step has safety_level C (Sensitive) or D (Destructive).
       - If yes, set requires_approval=True and transition to AWAITING_APPROVAL.
       - Otherwise, transition to EXECUTING.
    """
    def __init__(self):
        self.state: AgentState = AgentState.IDLE

    def transition_to(self, new_state: AgentState) -> None:
        """Update current agent state."""
        raise NotImplementedError("TODO: Chiranthan Rk - Implement transition_to")

    def build_plan(self, session_id: str, goal: str, steps: List[WorkflowStep]) -> ActionPlan:
        """Construct an ActionPlan and trigger appropriate state transition."""
        raise NotImplementedError("TODO: Chiranthan Rk - Implement build_plan")
