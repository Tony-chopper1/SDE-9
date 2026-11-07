/**
 * TypeScript interfaces for the Agentic Workflow & Tool Executor module.
 *
 * These types mirror the Pydantic models defined in `packages/agentic_workflow/models.py`
 * and are used as the frontend contract for all workflow-related API responses.
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
 *
 * Valid transitions:
 * ```
 * IDLE → LISTENING → PLANNING → AWAITING_APPROVAL → EXECUTING → VERIFYING → RESPONDING → IDLE
 * Any state → ERROR
 * ERROR → IDLE
 * ```
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

/** Lifecycle status of an individual workflow step. */
export type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "rejected";

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
}
