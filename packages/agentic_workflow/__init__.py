"""
Agentic Workflow & Tool Executor module.

Provides models, finite state machine, DAG dependency validation, allow-listed
tool registry, approval management, safe audit trails, and resilient mock execution for agentic tasks.
"""

from packages.agentic_workflow.approval import (
    ApprovalError,
    ApprovalExpiredError,
    ApprovalManager,
    ApprovalNotFoundError,
)
from packages.agentic_workflow.mock_executor import (
    DEFAULT_TOOL_SPECS,
    ExecutionCancelledError,
    MockToolExecutor,
    ToolExecutionTimeoutError,
)
from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
    AuditEvent,
    PermissionScope,
    PlanStatus,
    SafetyLevel,
    ToolResult,
    ToolSpec,
    WorkflowPlan,
    WorkflowResult,
    WorkflowStep,
    highest_safety_level,
)
from packages.agentic_workflow.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolParameterError,
    ToolRegistry,
)
from packages.agentic_workflow.state_machine import (
    AgentStateMachine,
    InvalidTransitionError,
    StateTransitionRecord,
)
from packages.agentic_workflow.validator import (
    CircularDependencyError,
    MissingDependencyError,
    PlanValidationError,
    PlanValidator,
)

__all__ = [
    # Models & Enums
    "SafetyLevel",
    "AgentState",
    "PermissionScope",
    "ApprovalStatus",
    "PlanStatus",
    "WorkflowStep",
    "WorkflowPlan",
    "ActionPlan",
    "ToolSpec",
    "DEFAULT_TOOL_SPECS",
    "ApprovalRequest",
    "AuditEvent",
    "WorkflowResult",
    "ToolResult",
    "highest_safety_level",
    # State Machine
    "AgentStateMachine",
    "InvalidTransitionError",
    "StateTransitionRecord",
    # Validation & DAG
    "PlanValidator",
    "PlanValidationError",
    "CircularDependencyError",
    "MissingDependencyError",
    # Tool Registry & Permissions
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolParameterError",
    "PermissionDeniedError",
    # Approval Manager
    "ApprovalManager",
    "ApprovalError",
    "ApprovalNotFoundError",
    "ApprovalExpiredError",
    # Executor
    "MockToolExecutor",
    "ExecutionCancelledError",
    "ToolExecutionTimeoutError",
]
