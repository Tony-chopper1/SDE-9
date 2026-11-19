/**
 * Type declarations for the Agentic Workflow progress visualization.
 * Strictly adheres to verified contracts from packages/agentic_workflow/types.ts
 * and models.py without speculative or unverified fields.
 */

export type SafetyLevel = 'A' | 'B' | 'C' | 'D';

export type PlanStatus =
  | 'PENDING'
  | 'PLANNING'
  | 'AWAITING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXPIRED'
  | 'EXECUTING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type StepStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'rejected'
  | 'cancelled';

export interface WorkflowStep {
  id: string;
  step_number: number;
  description: string;
  tool_name: string;
  parameters?: Record<string, unknown>;
  safety_level: SafetyLevel;
  status: StepStatus;
  result?: unknown;
  error?: string;
  retry_count?: number;
  started_at?: number;
  completed_at?: number;
  execution_logs?: string[];
}

export interface ActionPlan {
  plan_id: string;
  session_id: string;
  goal: string;
  steps: WorkflowStep[];
  current_step_index: number;
  overall_safety_level: SafetyLevel;
  requires_approval: boolean;
  status: PlanStatus;
  created_at: number;
  approved_at?: number;
  rejected_at?: number;
  rejection_reason?: string;
  execution_logs?: string[];
}

export interface WorkflowStepUpdatePayload {
  plan_id?: string;
  step_id?: string;
  id?: string;
  step_number?: number;
  status: StepStatus;
  tool_name?: string;
  result?: unknown;
  error?: string;
}

export interface WorkflowPlanPayload {
  plan?: ActionPlan;
  plan_id?: string;
  session_id?: string;
  goal?: string;
  steps?: WorkflowStep[];
  current_step_index?: number;
  overall_safety_level?: SafetyLevel;
  requires_approval?: boolean;
  status?: PlanStatus;
  created_at?: number;
}

export type ApprovalStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'EXPIRED';

export interface ApprovalRequest {
  request_id: string;
  plan_id: string;
  session_id: string;
  safety_level: SafetyLevel;
  status: ApprovalStatus;
  expires_at?: number;
  decided_at?: number;
  decided_by?: string;
  reason?: string;
  created_at: number;
  action?: string;
  description?: string;
  tool_name?: string;
  step_number?: number;
  step_id?: string;
  parameters?: Record<string, unknown>;
  risks?: string[];
  risk_assessment?: string;
}

export type ApprovalDecision = 'APPROVED' | 'REJECTED';

export interface ApprovalDecisionRecord {
  request_id: string;
  plan_id: string;
  decision: ApprovalDecision;
  decided_at: number;
  reason?: string;
}

