"""
Pydantic models for the Agentic Workflow & Tool Executor module.

Defines safety classification enums, agent lifecycle states, permission scopes,
approval requests, safe audit events, workflow schemas (WorkflowPlan, WorkflowStep,
ToolSpec, ApprovalRequest, WorkflowResult), and tool result contracts.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

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
        WORKSPACE_WRITE: File modifications within the workspace boundary.
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
# Tool Specification Model
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    """Specification of an authorized tool in the agentic workflow pipeline.

    This is the single canonical definition of a tool contract, used by both
    the mock executor and the tool registry.  ``registry.py`` imports this
    class directly — do **not** redefine it elsewhere.

    Attributes:
        name: Dot-namespaced tool identifier (e.g. ``"file.search"``).
        description: Human-readable summary of tool functionality.
        safety_level: Default risk classification governing approval requirements.
        is_idempotent: Whether repeated invocations produce identical results without side-effects.
        parameters: Loose key-value mapping of parameter names to type strings (informational).
        required_parameters: Mapping of parameter name → expected Python type used for
            schema validation.  An empty dict means no parameters are required.
        optional_parameters: Mapping of parameter name → expected Python type for
            parameters that may optionally be supplied.
        permission_scope: Required permission boundary to invoke this tool.
    """

    name: str
    description: str = ""
    safety_level: SafetyLevel = SafetyLevel.A
    is_idempotent: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required_parameters: Dict[str, Any] = Field(default_factory=dict)
    optional_parameters: Dict[str, Any] = Field(default_factory=dict)
    permission_scope: PermissionScope = PermissionScope.READ_ONLY


# ---------------------------------------------------------------------------
# Workflow Data Models
# ---------------------------------------------------------------------------


class WorkflowStep(BaseModel):
    """A single discrete action within a :class:`WorkflowPlan`.

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
        depends_on: Optional list of prerequisite step IDs that must complete first.
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


class AuditEvent(BaseModel):
    """Safe audit trail entry recording human-in-the-loop decisions.

    Contains step ID, decision rendered, optional rationale, and timestamp.
    Explicitly contains NO sensitive arguments or tool parameters.

    Attributes:
        step_id: Identifier of the workflow step associated with the decision (if any).
        decision: Decision rendered (e.g. 'APPROVED', 'REJECTED', 'EXPIRED').
        reason: Optional human- or system-supplied rationale for the decision.
        timestamp: Unix timestamp (seconds) when the event occurred.
        request_id: Optional approval request ID.
        plan_id: Optional action plan ID.
    """

    step_id: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)
    request_id: Optional[str] = None
    plan_id: Optional[str] = None


class WorkflowPlan(BaseModel):
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
        audit_trail: Safe audit events recorded during decision gates.
    """

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    goal: str
    steps: List[WorkflowStep] = Field(default_factory=list)
    current_step_index: int = 0
    overall_safety_level: SafetyLevel = SafetyLevel.A
    requires_approval: bool = False
    status: Union[PlanStatus, str] = PlanStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    approved_at: Optional[float] = None
    rejected_at: Optional[float] = None
    rejection_reason: Optional[str] = None
    execution_logs: List[str] = Field(default_factory=list)
    audit_trail: List[AuditEvent] = Field(default_factory=list)


# Backward compatibility alias for Week 1 codebase
ActionPlan = WorkflowPlan


class ApprovalRequest(BaseModel):
    """Formal request for human approval before executing sensitive workflow steps.

    Attributes:
        request_id: Unique identifier for the approval request.
        plan_id: Identifier of the associated :class:`WorkflowPlan`.
        session_id: Session identifier of the originating interaction.
        safety_level: Severity level triggering the approval requirement.
        status: Current status (:class:`ApprovalStatus` or str).
        expires_at: Epoch timestamp after which the request becomes expired.
        decided_at: Epoch timestamp when the decision was recorded.
        decided_by: Username or identifier of the deciding entity.
        reason: Optional human-provided justification for the decision.
        created_at: Epoch timestamp of creation.
        step_id: Optional identifier of the workflow step requiring approval.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    session_id: str
    safety_level: SafetyLevel
    status: Union[ApprovalStatus, str] = ApprovalStatus.PENDING
    expires_at: Optional[float] = None
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    step_id: Optional[str] = None


class WorkflowResult(BaseModel):
    """Result returned by the tool executor after attempting a tool invocation.

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


# Backward compatibility alias
ToolResult = WorkflowResult
