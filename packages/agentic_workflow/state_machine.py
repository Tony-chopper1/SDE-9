"""
Finite state machine for the Agentic Workflow module.

Manages the full lifecycle of an agent session: state transitions with
validation, plan construction with safety classification, human-approval
gating, DAG topological execution, and structured error handling.
"""

from __future__ import annotations

import time
import uuid
from typing import Collection, Dict, List, Optional, Tuple, Union

from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    PermissionScope,
    PlanStatus,
    SafetyLevel,
    WorkflowPlan,
    WorkflowStep,
    highest_safety_level,
)
from packages.agentic_workflow.validator import PlanValidator


# ---------------------------------------------------------------------------
# Transition Table
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: Dict[AgentState, List[AgentState]] = {
    AgentState.IDLE: [AgentState.LISTENING, AgentState.ERROR],
    AgentState.LISTENING: [AgentState.PLANNING, AgentState.IDLE, AgentState.ERROR],
    AgentState.PLANNING: [
        AgentState.AWAITING_APPROVAL,
        AgentState.EXECUTING,
        AgentState.ERROR,
    ],
    AgentState.AWAITING_APPROVAL: [
        AgentState.EXECUTING,
        AgentState.IDLE,
        AgentState.ERROR,
    ],
    AgentState.EXECUTING: [AgentState.VERIFYING, AgentState.ERROR],
    AgentState.VERIFYING: [AgentState.RESPONDING, AgentState.ERROR],
    AgentState.RESPONDING: [AgentState.IDLE, AgentState.ERROR],
    AgentState.ERROR: [AgentState.IDLE],
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not permitted by the FSM rules."""


# ---------------------------------------------------------------------------
# State Transition Record
# ---------------------------------------------------------------------------


class StateTransitionRecord:
    """Immutable record of a single FSM state transition.

    Attributes:
        from_state: The originating state.
        to_state: The destination state.
        timestamp: Unix epoch seconds when the transition occurred.
        metadata: Optional contextual data associated with the transition.
    """

    __slots__ = ("from_state", "to_state", "timestamp", "metadata")

    def __init__(
        self,
        from_state: AgentState,
        to_state: AgentState,
        timestamp: float,
        metadata: Optional[Dict] = None,
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.timestamp = timestamp
        self.metadata = metadata or {}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"StateTransitionRecord({self.from_state!r} → {self.to_state!r} "
            f"@ {self.timestamp})"
        )


# ---------------------------------------------------------------------------
# Agent State Machine
# ---------------------------------------------------------------------------


class AgentStateMachine:
    """Finite state machine governing multi-step agentic decision loops.

    Features:
        * Enforces valid state transitions with comprehensive history tracking.
        * Integrates :class:`PlanValidator` for DAG cycle and dependency validation.
        * Enforces approval gate rules for sensitive / destructive plans.
        * Executes plans in DAG topological order via :meth:`execute_plan`.
        * Provides robust error recovery paths via :meth:`handle_error` and :meth:`reset`.
    """

    def __init__(self) -> None:
        self.state: AgentState = AgentState.IDLE
        self.current_plan: Optional[ActionPlan] = None
        self.error_context: Optional[Dict] = None
        self.transition_history: List[StateTransitionRecord] = []

    # ------------------------------------------------------------------
    # Core Transition Primitives
    # ------------------------------------------------------------------

    def transition_to(self, new_state: AgentState, metadata: Optional[Dict] = None) -> None:
        """Attempt a validated transition to *new_state*.

        Raises:
            InvalidTransitionError: If the transition is not allowed from the current state.
        """
        allowed = _VALID_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Transition {self.state!r} → {new_state!r} is not permitted. "
                f"Allowed targets: {[s.value for s in allowed]}"
            )
        record = StateTransitionRecord(
            from_state=self.state,
            to_state=new_state,
            timestamp=time.time(),
            metadata=metadata,
        )
        self.transition_history.append(record)
        self.state = new_state

    def can_transition_to(self, target: AgentState) -> bool:
        """Return ``True`` if transitioning to *target* is currently valid."""
        return target in _VALID_TRANSITIONS.get(self.state, [])

    # ------------------------------------------------------------------
    # Plan Construction & Validation
    # ------------------------------------------------------------------

    def build_plan(
        self,
        session_id: str,
        goal: str,
        steps: List[WorkflowStep],
        validate: bool = True,
    ) -> ActionPlan:
        """Construct an :class:`ActionPlan` and apply the safety gate.

        If *validate* is True, runs :class:`PlanValidator` to check for
        missing dependencies and circular dependency cycles.

        Args:
            session_id: Session identifier.
            goal: Natural-language objective.
            steps: List of workflow steps.
            validate: Whether to validate DAG dependencies (default: True).

        Returns:
            Constructed and validated :class:`ActionPlan`.

        Raises:
            InvalidTransitionError: If not in PLANNING state.
            MissingDependencyError: If a step depends on an unlisted step ID.
            CircularDependencyError: If steps contain cyclic dependencies.
        """
        if self.state != AgentState.PLANNING:
            raise InvalidTransitionError(
                f"build_plan() requires state PLANNING; current state is {self.state!r}."
            )

        if validate and steps:
            PlanValidator.validate(steps)

        safety_levels = [step.safety_level for step in steps] if steps else [SafetyLevel.A]
        overall = highest_safety_level(safety_levels)
        needs_approval = overall in (SafetyLevel.C, SafetyLevel.D)

        plan = ActionPlan(
            plan_id=str(uuid.uuid4()),
            session_id=session_id,
            goal=goal,
            steps=list(steps),
            overall_safety_level=overall,
            requires_approval=needs_approval,
            status=PlanStatus.AWAITING_APPROVAL if needs_approval else PlanStatus.PLANNING,
        )
        self.current_plan = plan

        if needs_approval:
            self.transition_to(
                AgentState.AWAITING_APPROVAL,
                metadata={"plan_id": plan.plan_id, "overall_safety_level": overall.value},
            )
        else:
            self.transition_to(
                AgentState.EXECUTING,
                metadata={"plan_id": plan.plan_id, "overall_safety_level": overall.value},
            )

        return plan

    # ------------------------------------------------------------------
    # Approval Handling
    # ------------------------------------------------------------------

    def approve_plan(self) -> ActionPlan:
        """Approve the pending plan and transition to ``EXECUTING``."""
        if self.state != AgentState.AWAITING_APPROVAL:
            raise InvalidTransitionError(
                f"approve_plan() requires state AWAITING_APPROVAL; current state is {self.state!r}."
            )
        if self.current_plan is None:
            raise RuntimeError("No current plan exists to approve.")

        now = time.time()
        self.current_plan.approved_at = now
        self.current_plan.status = PlanStatus.APPROVED
        self.current_plan.execution_logs.append(
            f"[{now}] Plan approved; transitioning to EXECUTING."
        )
        self.transition_to(
            AgentState.EXECUTING,
            metadata={"plan_id": self.current_plan.plan_id, "action": "approved"},
        )
        return self.current_plan

    def reject_plan(self, reason: str) -> ActionPlan:
        """Reject the pending plan, mark steps as rejected, and return to ``IDLE``."""
        if self.state != AgentState.AWAITING_APPROVAL:
            raise InvalidTransitionError(
                f"reject_plan() requires state AWAITING_APPROVAL; current state is {self.state!r}."
            )
        if self.current_plan is None:
            raise RuntimeError("No current plan exists to reject.")

        now = time.time()
        self.current_plan.rejected_at = now
        self.current_plan.rejection_reason = reason
        self.current_plan.status = PlanStatus.REJECTED
        self.current_plan.execution_logs.append(f"[{now}] Plan rejected: {reason}")

        for step in self.current_plan.steps:
            if step.status == "pending":
                step.status = "rejected"

        self.transition_to(
            AgentState.IDLE,
            metadata={
                "plan_id": self.current_plan.plan_id,
                "action": "rejected",
                "reason": reason,
            },
        )
        rejected_plan = self.current_plan
        self.current_plan = None
        return rejected_plan

    # ------------------------------------------------------------------
    # Plan Execution in Topological DAG Order
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        executor: Optional[Any] = None,
        granted_scopes: Optional[Collection[PermissionScope]] = None,
        approval_manager: Optional[Any] = None,
    ) -> ActionPlan:
        """Execute the active plan's steps in prerequisite DAG topological order.

        Transitions:
            EXECUTING → VERIFYING → RESPONDING → IDLE (on success)
            EXECUTING → ERROR (on step failure, cancellation, or approval block)

        Args:
            executor: Instance of :class:`MockToolExecutor`. Created if None.
            granted_scopes: Scopes granted to caller for tool permission checking.
            approval_manager: Optional :class:`ApprovalManager` to verify approval gate.

        Returns:
            The executed :class:`ActionPlan`.

        Raises:
            RuntimeError: If there is no current plan.
            PermissionError: If execution is blocked by the approval gate.
        """
        if self.current_plan is None:
            raise RuntimeError("No active plan to execute.")

        if self.state != AgentState.EXECUTING:
            raise InvalidTransitionError(
                f"execute_plan() requires state EXECUTING; current state is {self.state!r}."
            )

        # Non-negotiable Approval Safety Check
        if approval_manager is not None:
            if not approval_manager.is_execution_permitted(self.current_plan):
                self.handle_error("Execution blocked: Plan approval is missing, rejected, or expired.")
                raise PermissionError("Plan execution is not permitted by approval gate.")
        else:
            if self.current_plan.requires_approval and self.current_plan.approved_at is None:
                self.handle_error("Execution blocked: Plan requires approval.")
                raise PermissionError("Plan requires approval before execution.")
            if self.current_plan.rejected_at is not None:
                self.handle_error("Execution blocked: Plan has been rejected.")
                raise PermissionError("Plan was rejected.")

        from packages.agentic_workflow.mock_executor import MockToolExecutor

        exec_instance = executor or MockToolExecutor()

        if exec_instance.is_cancelled:
            self.current_plan.status = PlanStatus.CANCELLED
            self.handle_error("Execution cancelled before starting.")
            return self.current_plan

        # Compute DAG topological order
        ordered_ids = PlanValidator.get_topological_order(self.current_plan)
        step_map = {s.id: s for s in self.current_plan.steps}

        self.current_plan.status = PlanStatus.EXECUTING

        for idx, step_id in enumerate(ordered_ids):
            if exec_instance.is_cancelled:
                self.current_plan.status = PlanStatus.CANCELLED
                self.handle_error("Execution cancelled during plan steps.")
                return self.current_plan

            step = step_map[step_id]
            self.current_plan.current_step_index = idx

            res = exec_instance.execute_step(
                step=step,
                granted_scopes=granted_scopes,
            )

            if not res.success:
                self.current_plan.status = PlanStatus.FAILED
                self.handle_error(
                    f"Execution failed at step '{step.id}' ({step.tool_name}): {res.error}"
                )
                return self.current_plan

        # All steps succeeded: advance through verification and response to IDLE
        self.transition_to(AgentState.VERIFYING)
        self.transition_to(AgentState.RESPONDING)
        self.transition_to(AgentState.IDLE)

        self.current_plan.status = PlanStatus.COMPLETED
        return self.current_plan

    # ------------------------------------------------------------------
    # Error Handling & Recovery
    # ------------------------------------------------------------------

    def handle_error(self, error_message: str) -> Dict:
        """Transition to ``ERROR`` and capture recovery metadata."""
        previous_state = self.state
        recovery_metadata: Dict = {
            "error_message": error_message,
            "previous_state": previous_state.value,
            "timestamp": time.time(),
            "plan_id": self.current_plan.plan_id if self.current_plan else None,
        }
        self.error_context = recovery_metadata
        self.transition_to(AgentState.ERROR, metadata=recovery_metadata)
        return recovery_metadata

    def reset(self) -> None:
        """Recover from ``ERROR`` state and return the machine to ``IDLE``."""
        if self.state != AgentState.ERROR:
            raise InvalidTransitionError(
                f"reset() can only be called from ERROR state; current state is {self.state!r}."
            )
        self.transition_to(AgentState.IDLE, metadata={"action": "reset_after_error"})
        self.current_plan = None
        self.error_context = None

    # ------------------------------------------------------------------
    # Inspection Helpers
    # ------------------------------------------------------------------

    def get_transition_history(self) -> List[Tuple[str, str, float]]:
        """Return the transition history as a list of ``(from, to, timestamp)`` tuples."""
        return [
            (r.from_state.value, r.to_state.value, r.timestamp)
            for r in self.transition_history
        ]
