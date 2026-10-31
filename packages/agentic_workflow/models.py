"""
Agentic Workflow and Tool Executor
Owner: Chiranthan Rk (feature/agentic-workflow)
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time


class SafetyLevel(str, Enum):
    A = "A"  # Informational (no approval needed)
    B = "B"  # Low risk (auto-approve + notify)
    C = "C"  # Sensitive (explicit approval required)
    D = "D"  # Destructive (explicit approval required)


class AgentState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    RESPONDING = "RESPONDING"
    ERROR = "ERROR"


class WorkflowStep(BaseModel):
    id: str
    step_number: int
    description: str
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    safety_level: SafetyLevel
    status: str = "pending"  # pending | running | completed | failed | rejected
    result: Optional[Any] = None
    error: Optional[str] = None


class ActionPlan(BaseModel):
    plan_id: str
    session_id: str
    goal: str
    steps: List[WorkflowStep] = Field(default_factory=list)
    current_step_index: int = 0
    overall_safety_level: SafetyLevel
    requires_approval: bool
    created_at: float = Field(default_factory=time.time)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: Any
    duration_ms: float
    error: Optional[str] = None
