"""
Pydantic models for the Agentic Workflow & Tool Executor module.

Defines safety classification enums, agent lifecycle states, workflow schemas
(WorkflowPlan, WorkflowStep, ToolSpec, ApprovalRequest, WorkflowResult),
and supporting contracts.
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
        A: Informational – read-only, harmless, no side-effects; auto-approved.
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


# ---------------------------------------------------------------------------
# Workflow Data Models
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    """Specification defining parameters, safety level, and metadata for a tool.

    Attributes:
        name: Dot-namespaced or identifier name of the tool (e.g. ``"calc.evaluate"``).
        description: Human-readable description of what the tool performs.
        safety_level: Risk classification for tool invocation.
        is_idempotent: Whether repeated invocations produce identical results safely.
        parameters: JSON Schema or dict mapping parameter names to expected types.
        required_parameters: List of mandatory parameter names.
    """

    name: str
    description: str = ""
    safety_level: SafetyLevel = SafetyLevel.A
    is_idempotent: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)
    required_parameters: List[str] = Field(default_factory=list)


class WorkflowStep(BaseModel):
    """A single discrete action within a :class:`WorkflowPlan`.

    Attributes:
        id: Unique identifier for this step (UUID string).
        step_number: 1-based ordering index within the plan.
        description: Human-readable description of the action.
        tool_name: Dot-namespaced tool identifier (e.g. ``"file.search"``, ``"calc.evaluate"``).
        parameters: Key-value arguments forwarded to the tool executor.
        safety_level: Risk classification governing approval requirements.
        status: Lifecycle status – one of ``pending``, ``running``,
            ``completed``, ``failed``, ``rejected``.
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
    depends_on: List[str] = Field(default_factory=list)
    timeout_seconds: Optional[float] = None
    is_idempotent: bool = True


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
    created_at: float = Field(default_factory=time.time)
    approved_at: Optional[float] = None
    rejected_at: Optional[float] = None
    rejection_reason: Optional[str] = None
    execution_logs: List[str] = Field(default_factory=list)


# Backward compatibility alias for Week 1 codebase
ActionPlan = WorkflowPlan


class ApprovalRequest(BaseModel):
    """Formal request for human approval before executing sensitive workflow steps.

    Attributes:
        request_id: Unique identifier for the approval request.
        plan_id: Identifier of the associated :class:`WorkflowPlan`.
        session_id: Session identifier of the originating interaction.
        safety_level: Severity level triggering the approval requirement.
        status: Current status (e.g. ``"PENDING"``, ``"APPROVED"``, ``"REJECTED"``).
        expires_at: Epoch timestamp after which the request becomes expired.
        decided_at: Epoch timestamp when the decision was recorded.
        decided_by: Username or identifier of the deciding entity.
        reason: Optional human-provided justification for the decision.
        created_at: Epoch timestamp of creation.
    """

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str
    session_id: str
    safety_level: SafetyLevel
    status: str = "PENDING"
    expires_at: Optional[float] = None
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    reason: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


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


# Backward compatibility alias for Week 1 codebase
ToolResult = WorkflowResult
