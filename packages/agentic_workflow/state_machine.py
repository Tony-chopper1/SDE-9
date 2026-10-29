import time
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
    """
    def __init__(self):
        self.state: AgentState = AgentState.IDLE

    def transition_to(self, new_state: AgentState) -> None:
        self.state = new_state

    def build_plan(self, session_id: str, goal: str, steps: List[WorkflowStep]) -> ActionPlan:
        self.transition_to(AgentState.PLANNING)

        has_sensitive = any(s.safety_level in (SafetyLevel.C, SafetyLevel.D) for s in steps)
        if any(s.safety_level == SafetyLevel.D for s in steps):
            overall_safety = SafetyLevel.D
        elif any(s.safety_level == SafetyLevel.C for s in steps):
            overall_safety = SafetyLevel.C
        else:
            overall_safety = SafetyLevel.A

        plan = ActionPlan(
            plan_id=f"plan-{int(time.time() * 1000)}",
            session_id=session_id,
            goal=goal,
            steps=steps,
            current_step_index=0,
            overall_safety_level=overall_safety,
            requires_approval=has_sensitive,
        )

        if has_sensitive:
            self.transition_to(AgentState.AWAITING_APPROVAL)
        else:
            self.transition_to(AgentState.EXECUTING)

        return plan
