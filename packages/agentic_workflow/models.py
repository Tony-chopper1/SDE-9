"""
Pydantic models for the Agentic Workflow & Tool Executor module.

Defines safety classification enums, agent lifecycle states, permission scopes,
approval requests, workflow data structures, and tool result contracts used
throughout the agentic pipeline.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SafetyLevel(str, Enum):
    """Classification of action risk, determining whether human approval is required.

    Levels:
        A: Informational – read-only, no side-effects; auto-approved.
        B: Low Risk – minor writes or notifications; auto-approved with audit log.
        C: Sensitive – modifies important state; requires explicit human approval.
        D: Destructive – irreversible or high-impact actions; requires explicit human approval.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"


# Ordered severity for comparison (higher index = more severe)
_SAFETY_ORDER: list[SafetyLevel] = [
    SafetyLevel.A,
    SafetyLevel.B,
    SafetyLevel.C,
    SafetyLevel.D,
]


def highest_safety_level(levels: List[SafetyLevel]) -> SafetyLevel:
    """Return the most severe :class:`SafetyLevel` from *levels*.

    Args:
        levels: Non-empty list of safety levels to compare.

    Returns:
        The :class:`SafetyLevel` with the highest severity.

    Raises:
        ValueError: If *levels* is empty.
    """
    if not levels:
        raise ValueError("levels must not be empty")
    return max(levels, key=lambda sl: _SAFETY_ORDER.index(sl))


class AgentState(str, Enum):
    """Finite states of the agentic decision loop.

    Transitions:
        IDLE → LISTENING → PLANNING → AWAITING_APPROVAL → EXECUTING → VERIFYING → RESPONDING → IDLE
        Any state → ERROR (on unrecoverable failure)
        ERROR → IDLE (on recovery/reset)
    """

    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESPONDING = "RESPONDING"
    ERROR = "ERROR"


class PermissionScope(str, Enum):
    """Permission boundaries required to invoke specific tools.

    Scopes:
        READ_ONLY: Read-only inspection and querying (e.g. file search, calculator).
        WORKSPACE_WRITE: File modifications within the workspace boundary (e.g. file move).
        SYSTEM_EXEC: Privileged system-level execution.
    """

    READ_ONLY = "READ_ONLY"
    WORKSPACE_WRITE = "WORKSPACE_WRITE"
    SYSTEM_EXEC = "SYSTEM_EXEC"


class ApprovalStatus(str, Enum):
    """Lifecycle status of a human-in-the-loop approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PlanStatus(str, Enum):
    """Execution status of a workflow plan."""

    PENDING = "PENDING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Workflow Data Models
# ---------------------------------------------------------------------------


class WorkflowStep(BaseModel):
    """A single discrete action within an :class:`ActionPlan`.

    Attributes:
        id: Unique identifier for this step (UUID string).
        step_number: 1-based ordering index within the plan.
        description: Human-readable description of the action.
        tool_name: Dot-namespaced tool identifier (e.g. ``"file.search"``).
        parameters: Key-value arguments forwarded to the tool executor.
        safety_level: Risk classification governing approval requirements.
        status: Lifecycle status – one of ``pending``, ``running``,
            ``completed``, ``failed``, ``rejected``, ``cancelled``.
        result: Arbitrary output returned by the tool executor upon success.
        error: Error message populated on failure.
        retry_count: Number of execution attempts made for this step.
        started_at: Unix timestamp (seconds) when execution began, or ``None``.
        completed_at: Unix timestamp (seconds) when execution ended, or ``None``.
        execution_logs: Ordered list of log entries emitted during execution.
        depends_on: List of step IDs that must complete before this step runs.
        timeout_seconds: Per-step execution timeout in seconds.
        is_idempotent: Whether this step can safely be retried on failure.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int
    description: str
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    safety_level: SafetyLevel
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    # Execution metadata
    retry_count: int = 0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    execution_logs: List[str] = Field(default_factory=list)
    # Week 2 Enhancements
    depends_on: List[str] = Field(default_factory=list)
    timeout_seconds: Optional[float] = None
    is_idempotent: bool = True


class ActionPlan(BaseModel):
    """An ordered collection of :class:`WorkflowStep` objects representing a multi-step goal.

    Attributes:
        plan_id: Unique plan identifier (UUID string).
        session_id: Identifier of the user session that triggered this plan.
        goal: Natural-language description of the overall objective.
        steps: Ordered list of workflow steps to execute.
        current_step_index: Zero-based index of the currently active step.
        overall_safety_level: Highest :class:`SafetyLevel` across all steps.
        requires_approval: ``True`` when at least one step is level C or D.
        status: Lifecycle status of the overall plan.
        created_at: Unix timestamp (seconds) of plan creation.
        approved_at: Unix timestamp (seconds) when the plan was approved, or ``None``.
        rejected_at: Unix timestamp (seconds) when the plan was rejected, or ``None``.
        rejection_reason: Operator-supplied reason for rejection, or ``None``.
        execution_logs: Top-level log entries for the overall plan lifecycle.
    """

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    goal: str
    steps: List[WorkflowStep] = Field(default_factory=list)
    current_step_index: int = 0
    overall_safety_level: SafetyLevel = SafetyLevel.A
    requires_approval: bool = False
    status: PlanStatus = PlanStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    approved_at: Optional[float] = None
    rejected_at: Optional[float] = None
    rejection_reason: Optional[str] = None
    execution_logs: List[str] = Field(default_factory=list)


# Alias for compatibility with DAG validator and plan interfaces
WorkflowPlan = ActionPlan


class ApprovalRequest(BaseModel):
    """Formal request for human approval before executing a sensitive action plan.

    Attributes:
        request_id: Unique identifier for the approval request.
        plan_id: Identifier of the associated :class:`ActionPlan`.
        session_id: Session identifier of the user interaction.
        safety_level: Severity level triggering the approval requirement.
        status: Current approval status (:class:`ApprovalStatus`).
        expires_at: Epoch timestamp after which the request becomes expired.
        decided_at: Epoch timestamp when the decision was recorded.
        decided_by: Username or identity of the deciding entity.
        reason: Optional human-provided justification for decision.
        created_at: Epoch timestamp of creation.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    session_id: str
    safety_level: SafetyLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    expires_at: Optional[float] = None
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class ToolResult(BaseModel):
    """Result returned by the tool executor after attempting a single tool invocation.

    Attributes:
        tool_name: The dot-namespaced tool identifier that was executed.
        success: ``True`` if the tool completed without error.
        output: Arbitrary tool output (structured data, strings, etc.).
        duration_ms: Wall-clock execution time in milliseconds.
        error: Error description when ``success`` is ``False``, otherwise ``None``.
        timestamp: Unix timestamp (seconds) of result creation.
    """

    tool_name: str
    success: bool
    output: Any
    duration_ms: float
    error: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
