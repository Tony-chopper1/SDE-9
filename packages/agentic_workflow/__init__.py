"""
Agentic Workflow & Tool Executor module.

Provides models, finite state machine, DAG dependency validation, allow-listed
tool registry, approval management, and resilient mock execution for agentic tasks.
"""

from packages.agentic_workflow.approval import (
    ApprovalError,
    ApprovalExpiredError,
    ApprovalManager,
    ApprovalNotFoundError,
)
from packages.agentic_workflow.mock_executor import (
    ExecutionCancelledError,
    MockToolExecutor,
    ToolExecutionTimeoutError,
)
from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    ApprovalRequest,
    ApprovalStatus,
    PermissionScope,
    PlanStatus,
    SafetyLevel,
    ToolResult,
    WorkflowPlan,
    WorkflowStep,
    highest_safety_level,
)
from packages.agentic_workflow.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolParameterError,
    ToolRegistry,
    ToolSpec,
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
    "ActionPlan",
    "WorkflowPlan",
    "ApprovalRequest",
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
    "ToolSpec",
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
