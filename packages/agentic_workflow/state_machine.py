"""
Finite state machine for the Agentic Workflow module.

Manages the full lifecycle of an agent session: state transitions with
validation, plan construction with safety classification, human-approval
gating, and structured error handling with recovery metadata.
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Tuple

from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    SafetyLevel,
    WorkflowStep,
    highest_safety_level,
)

# ---------------------------------------------------------------------------
# Transition Table
# ---------------------------------------------------------------------------

# Maps each state to the set of states it is permitted to transition into.
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

    The FSM enforces valid state transitions, records full transition history
    with timestamps, applies a safety gate when building plans, and provides
    structured approval and error-recovery paths.

    Attributes:
        state: Current :class:`AgentState` of the machine.
        current_plan: The active :class:`ActionPlan`, if one has been built.
        error_context: Metadata captured on the most recent ERROR transition.
        transition_history: Ordered list of :class:`StateTransitionRecord` objects.

    Example::

        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        step = WorkflowStep(
            step_number=1,
            description="Search project files",
            tool_name="file.search",
            safety_level=SafetyLevel.A,
            parameters={"pattern": "*.py"},
        )
        plan = sm.build_plan(session_id="sess-1", goal="List Python files", steps=[step])
        # SafetyLevel A → auto-proceeds to EXECUTING
        assert sm.state == AgentState.EXECUTING
    """

    def __init__(self) -> None:
        self.state: AgentState = AgentState.IDLE
        self.current_plan: Optional[ActionPlan] = None
        self.error_context: Optional[Dict] = None
        self.transition_history: List[StateTransitionRecord] = []

    # ------------------------------------------------------------------
    # Core transition primitives
    # ------------------------------------------------------------------

    def transition_to(self, new_state: AgentState, metadata: Optional[Dict] = None) -> None:
        """Attempt a validated transition to *new_state*.

        Args:
            new_state: The target :class:`AgentState`.
            metadata: Optional context to attach to the transition record.

        Raises:
            InvalidTransitionError: If the transition from the current state
                to *new_state* is not defined in the FSM transition table.
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
        """Return ``True`` if transitioning to *target* is currently valid.

        Args:
            target: The :class:`AgentState` to test.

        Returns:
            ``True`` if the transition is permitted, ``False`` otherwise.
        """
        return target in _VALID_TRANSITIONS.get(self.state, [])

    # ------------------------------------------------------------------
    # Plan construction
    # ------------------------------------------------------------------

    def build_plan(
        self, session_id: str, goal: str, steps: List[WorkflowStep]
    ) -> ActionPlan:
        """Construct an :class:`ActionPlan` and apply the safety gate.

        If any step carries :attr:`SafetyLevel.C` (Sensitive) or
        :attr:`SafetyLevel.D` (Destructive), ``requires_approval`` is set to
        ``True`` and the machine transitions to ``AWAITING_APPROVAL``.
        Otherwise the machine transitions directly to ``EXECUTING``.

        The machine must be in ``PLANNING`` state before calling this method.

        Args:
            session_id: Identifier of the originating user session.
            goal: Natural-language description of the overall objective.
            steps: Ordered list of :class:`WorkflowStep` objects.

        Returns:
            The constructed :class:`ActionPlan`.

        Raises:
            InvalidTransitionError: If the machine is not currently in the
                ``PLANNING`` state when this method is called.
        """
        if self.state != AgentState.PLANNING:
            raise InvalidTransitionError(
                f"build_plan() requires state PLANNING; current state is {self.state!r}."
            )

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
    # Approval handling
    # ------------------------------------------------------------------

    def approve_plan(self) -> ActionPlan:
        """Approve the current pending plan and transition to ``EXECUTING``.

        Returns:
            The approved :class:`ActionPlan` with ``approved_at`` timestamp set.

        Raises:
            InvalidTransitionError: If the machine is not in ``AWAITING_APPROVAL``.
            RuntimeError: If there is no current plan to approve.
        """
        if self.state != AgentState.AWAITING_APPROVAL:
            raise InvalidTransitionError(
                f"approve_plan() requires state AWAITING_APPROVAL; current state is {self.state!r}."
            )
        if self.current_plan is None:
            raise RuntimeError("No current plan exists to approve.")

        self.current_plan.approved_at = time.time()
        self.current_plan.execution_logs.append(
            f"[{time.time()}] Plan approved; transitioning to EXECUTING."
        )
        self.transition_to(
            AgentState.EXECUTING,
            metadata={"plan_id": self.current_plan.plan_id, "action": "approved"},
        )
        return self.current_plan

    def reject_plan(self, reason: str) -> ActionPlan:
        """Reject the current pending plan and return to ``IDLE``.

        Args:
            reason: Human-readable explanation for the rejection.

        Returns:
            The rejected :class:`ActionPlan` with ``rejected_at`` and
            ``rejection_reason`` populated.

        Raises:
            InvalidTransitionError: If the machine is not in ``AWAITING_APPROVAL``.
            RuntimeError: If there is no current plan to reject.
        """
        if self.state != AgentState.AWAITING_APPROVAL:
            raise InvalidTransitionError(
                f"reject_plan() requires state AWAITING_APPROVAL; current state is {self.state!r}."
            )
        if self.current_plan is None:
            raise RuntimeError("No current plan exists to reject.")

        now = time.time()
        self.current_plan.rejected_at = now
        self.current_plan.rejection_reason = reason
        self.current_plan.execution_logs.append(
            f"[{now}] Plan rejected: {reason}"
        )
        # Mark all pending steps as rejected
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
    # Error handling and recovery
    # ------------------------------------------------------------------

    def handle_error(self, error_message: str) -> Dict:
        """Transition to ``ERROR`` and capture recovery metadata.

        Can be called from any state except ``ERROR`` itself (which requires
        a reset first).

        Args:
            error_message: Human-readable description of the failure.

        Returns:
            A dict containing ``error_message``, ``previous_state``,
            ``timestamp``, and ``plan_id`` (if a plan was active).
        """
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
        """Recover from ``ERROR`` state and return the machine to ``IDLE``.

        Also clears :attr:`current_plan` and :attr:`error_context`.

        Raises:
            InvalidTransitionError: If the machine is not in the ``ERROR`` state.
        """
        if self.state != AgentState.ERROR:
            raise InvalidTransitionError(
                f"reset() can only be called from ERROR state; current state is {self.state!r}."
            )
        self.transition_to(AgentState.IDLE, metadata={"action": "reset_after_error"})
        self.current_plan = None
        self.error_context = None

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def get_transition_history(self) -> List[Tuple[str, str, float]]:
        """Return the transition history as a list of ``(from, to, timestamp)`` tuples.

        Returns:
            A list of ``(from_state, to_state, timestamp)`` 3-tuples in
            chronological order.
        """
        return [
            (r.from_state.value, r.to_state.value, r.timestamp)
            for r in self.transition_history
        ]
