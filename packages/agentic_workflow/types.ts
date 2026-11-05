/**
 * TypeScript interfaces for the Agentic Workflow & Tool Executor module.
 *
 * Mirrors the Pydantic models defined in `packages/agentic_workflow/models.py`,
 * validator contracts, and approval requests for frontend and API consumer parity.
 *
 * @module agentic_workflow/types
 */

// ---------------------------------------------------------------------------
// Enumerations
// ---------------------------------------------------------------------------

/**
 * Risk classification of a workflow action.
 *
 * | Level | Label       | Approval Required |
 * |-------|-------------|-------------------|
 * | A     | Informational | No – auto-approved |
 * | B     | Low Risk    | No – auto-approved, audit logged |
 * | C     | Sensitive   | Yes – explicit human approval |
 * | D     | Destructive | Yes – explicit human approval |
 */
export type SafetyLevel = "A" | "B" | "C" | "D";

/**
 * Finite states of the agentic decision loop.
 */
export type AgentState =
  | "IDLE"
  | "LISTENING"
  | "PLANNING"
  | "AWAITING_APPROVAL"
  | "EXECUTING"
  | "VERIFYING"
  | "RESPONDING"
  | "ERROR";

/**
 * Permission boundary required to invoke specific tools.
 */
export type PermissionScope =
  | "READ_ONLY"
  | "WORKSPACE_WRITE"
  | "SYSTEM_EXEC";

/**
 * Lifecycle status of a human-in-the-loop approval request.
 */
export type ApprovalStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED";

/**
 * Execution status of an action plan.
 */
export type PlanStatus =
  | "PENDING"
  | "PLANNING"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "EXPIRED"
  | "EXECUTING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

/**
 * Lifecycle status of an individual workflow step.
 */
export type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "rejected"
  | "cancelled";

// ---------------------------------------------------------------------------
// Workflow Data Interfaces
// ---------------------------------------------------------------------------

/**
 * A single discrete action within an {@link ActionPlan}.
 */
export interface WorkflowStep {
  /** Unique identifier for this step (UUID string). */
  id: string;
  /** 1-based ordering index within the plan. */
  step_number: number;
  /** Human-readable description of the action. */
  description: string;
  /** Dot-namespaced tool identifier (e.g. `"file.search"`). */
  tool_name: string;
  /** Key-value arguments forwarded to the tool executor. */
  parameters: Record<string, unknown>;
  /** Risk classification governing approval requirements. */
  safety_level: SafetyLevel;
  /** Current lifecycle status of this step. */
  status: StepStatus;
  /** Arbitrary output returned by the tool executor on success. */
  result?: unknown;
  /** Error message on failure. */
  error?: string;
  /** Number of execution attempts made for this step. */
  retry_count: number;
  /** Unix timestamp (seconds) when execution began. */
  started_at?: number;
  /** Unix timestamp (seconds) when execution ended. */
  completed_at?: number;
  /** Ordered list of log entries emitted during execution. */
  execution_logs: string[];
  /** IDs of prerequisite steps that must complete before this step can execute. */
  depends_on: string[];
  /** Maximum execution duration in seconds before timing out. */
  timeout_seconds?: number;
  /** Whether the tool action is idempotent and safe to retry on failure. */
  is_idempotent: boolean;
}

/**
 * An ordered collection of {@link WorkflowStep} objects representing a multi-step goal.
 */
export interface ActionPlan {
  /** Unique plan identifier (UUID string). */
  plan_id: string;
  /** Identifier of the user session that triggered this plan. */
  session_id: string;
  /** Natural-language description of the overall objective. */
  goal: string;
  /** Ordered list of workflow steps to execute. */
  steps: WorkflowStep[];
  /** Zero-based index of the currently active step. */
  current_step_index: number;
  /** Highest {@link SafetyLevel} across all steps. */
  overall_safety_level: SafetyLevel;
  /** `true` when at least one step is level C or D. */
  requires_approval: boolean;
  /** Current lifecycle status of the overall plan. */
  status: PlanStatus;
  /** Unix timestamp (seconds) of plan creation. */
  created_at: number;
  /** Unix timestamp (seconds) when the plan was approved. */
  approved_at?: number;
  /** Unix timestamp (seconds) when the plan was rejected. */
  rejected_at?: number;
  /** Operator-supplied reason for rejection. */
  rejection_reason?: string;
  /** Top-level log entries for the overall plan lifecycle. */
  execution_logs: string[];
}

/**
 * Alias for {@link ActionPlan}.
 */
export type WorkflowPlan = ActionPlan;

/**
 * Formal request for human approval before executing sensitive workflow steps.
 */
export interface ApprovalRequest {
  /** Unique request identifier (UUID string). */
  request_id: string;
  /** Identifier of the plan requiring approval. */
  plan_id: string;
  /** Identifier of the originating session. */
  session_id: string;
  /** Severity level requiring human sign-off. */
  safety_level: SafetyLevel;
  /** Current status of the request. */
  status: ApprovalStatus;
  /** Unix timestamp when this request expires. */
  expires_at?: number;
  /** Unix timestamp when a decision was rendered. */
  decided_at?: number;
  /** Identity or username of the approving/rejecting entity. */
  decided_by?: string;
  /** Human-readable explanation or justification. */
  reason?: string;
  /** Unix timestamp of creation. */
  created_at: number;
}

/**
 * Result returned by the tool executor after a single tool invocation.
 */
export interface ToolResult {
  /** Dot-namespaced tool identifier that was executed. */
  tool_name: string;
  /** `true` if the tool completed without error. */
  success: boolean;
  /** Arbitrary tool output (structured data, strings, etc.). */
  output: unknown;
  /** Wall-clock execution time in milliseconds. */
  duration_ms: number;
  /** Error description when `success` is `false`. */
  error?: string;
  /** Unix timestamp (seconds) of result creation. */
  timestamp: number;
}

/**
 * Specification defining parameters, permissions, and behavior of a registered tool.
 */
export interface ToolSpec {
  name: string;
  permission_scope: PermissionScope;
  is_idempotent: boolean;
  safety_level: SafetyLevel;
  description: string;
}

// ---------------------------------------------------------------------------
// State Machine Supporting Types
// ---------------------------------------------------------------------------

/**
 * A single entry in the agent state transition history.
 */
export interface StateTransitionRecord {
  /** The state transitioned from. */
  from_state: AgentState;
  /** The state transitioned to. */
  to_state: AgentState;
  /** Unix timestamp (seconds) when the transition occurred. */
  timestamp: number;
  /** Optional contextual metadata for the transition. */
  metadata?: Record<string, unknown>;
}

/**
 * Error context attached to an {@link AgentState.ERROR} transition.
 */
export interface ErrorContext {
  /** Human-readable error description. */
  message: string;
  /** The state the agent was in when the error occurred. */
  previous_state: AgentState;
  /** Unix timestamp (seconds) of the error. */
  timestamp: number;
  /** Associated plan ID, if active. */
  plan_id?: string;
}
