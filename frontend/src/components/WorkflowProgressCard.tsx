import React, { useEffect, useRef, useState, useMemo } from 'react';
import { ActionPlan, StepStatus } from '../types/workflow';

export interface WorkflowProgressCardProps {
  plan: ActionPlan | null;
  isMockMode?: boolean;
  isDemoPlan?: boolean;
  onTriggerDemoPlan?: () => void;
  onClearPlan?: () => void;
}

export const WorkflowProgressCard: React.FC<WorkflowProgressCardProps> = ({
  plan,
  isMockMode = false,
  isDemoPlan = false,
  onTriggerDemoPlan,
  onClearPlan,
}) => {
  const [announcement, setAnnouncement] = useState<string>('');
  const prevSignatureRef = useRef<string>('');

  // Calculate progress: completed steps divided by total steps
  const { totalSteps, completedSteps, progressPercent } = useMemo(() => {
    if (!plan || !plan.steps || plan.steps.length === 0) {
      return { totalSteps: 0, completedSteps: 0, progressPercent: 0 };
    }
    const total = plan.steps.length;
    const completed = plan.steps.filter((s) => s.status === 'completed').length;
    const percent = Math.round((completed / total) * 100);
    return { totalSteps: total, completedSteps: completed, progressPercent: percent };
  }, [plan]);

  // Screen reader announcements that describe actual state changes without repeating
  useEffect(() => {
    if (!plan) {
      if (prevSignatureRef.current !== 'standby') {
        prevSignatureRef.current = 'standby';
        setAnnouncement('No active workflow plan. Agentic workflow is in standby.');
      }
      return;
    }

    const runningStep = plan.steps.find((s) => s.status === 'running');
    const failedStep = plan.steps.find((s) => s.status === 'failed');
    const rejectedStep = plan.steps.find((s) => s.status === 'rejected');

    const signature = `${plan.plan_id}:${plan.status}:${plan.steps
      .map((s) => `${s.step_number}-${s.status}`)
      .join(',')}`;

    if (prevSignatureRef.current !== signature) {
      prevSignatureRef.current = signature;

      if (plan.status === 'COMPLETED') {
        setAnnouncement(`Workflow completed successfully: ${plan.goal}`);
      } else if (failedStep) {
        setAnnouncement(
          `Workflow step ${failedStep.step_number} failed: ${failedStep.description}. ${
            failedStep.error ? `Error: ${failedStep.error}` : ''
          }`
        );
      } else if (rejectedStep) {
        setAnnouncement(
          `Workflow step ${rejectedStep.step_number} rejected: ${rejectedStep.description}`
        );
      } else if (runningStep) {
        setAnnouncement(
          `Workflow step ${runningStep.step_number} running: ${runningStep.description}`
        );
      } else if (plan.status === 'AWAITING_APPROVAL') {
        setAnnouncement(`Workflow awaiting approval for goal: ${plan.goal}`);
      } else {
        setAnnouncement(`Workflow active: ${plan.goal}. Status is ${plan.status}`);
      }
    }
  }, [plan]);

  const renderStatusIcon = (status: StepStatus) => {
    switch (status) {
      case 'completed':
        return <span className="step-icon step-icon-completed" aria-hidden="true">✓</span>;
      case 'running':
        return <span className="step-icon step-icon-running" aria-hidden="true">●</span>;
      case 'failed':
        return <span className="step-icon step-icon-failed" aria-hidden="true">✕</span>;
      case 'rejected':
        return <span className="step-icon step-icon-rejected" aria-hidden="true">⊘</span>;
      case 'cancelled':
        return <span className="step-icon step-icon-cancelled" aria-hidden="true">⊝</span>;
      case 'pending':
      default:
        return <span className="step-icon step-icon-pending" aria-hidden="true">○</span>;
    }
  };

  // Standby State
  if (!plan) {
    return (
      <section
        className="workflow-progress-card standby"
        aria-labelledby="workflow-heading-standby"
      >
        <div className="card-header">
          <div>
            <span className="section-eyebrow">AGENTIC WORKFLOW</span>
            <h2 id="workflow-heading-standby" className="card-title">
              Workflow Progress
            </h2>
          </div>
          <div className="card-header-badges">
            <span className="standby-badge" role="status" aria-label="Workflow status: Idle">
              IDLE
            </span>
          </div>
        </div>

        <div className="workflow-standby-body">
          <p className="workflow-standby-text">
            No active workflow plan. Spoken requests requiring multi-step tool execution (such as
            file operations, calculations, or data analysis) will generate and execute an action plan here.
          </p>

          {isMockMode && onTriggerDemoPlan && (
            <div className="mock-demo-trigger-box">
              <span className="mock-demo-label">SIMULATED TESTING</span>
              <p className="mock-demo-note">
                Backend services are operating in mock mode. You can load a simulated demo plan to
                evaluate workflow progression.
              </p>
              <button
                type="button"
                className="load-demo-plan-btn"
                onClick={onTriggerDemoPlan}
                aria-label="Load simulated demo workflow plan"
              >
                Load Simulated Demo Plan
              </button>
            </div>
          )}
        </div>

        {/* Screen Reader Live Region */}
        <div aria-live="polite" aria-atomic="true" className="sr-only">
          {announcement}
        </div>
      </section>
    );
  }

  // Active Workflow State
  return (
    <section
      className="workflow-progress-card active"
      aria-labelledby="workflow-heading-active"
    >
      <div className="card-header">
        <div className="workflow-header-info">
          <div className="workflow-eyebrow-row">
            <span className="section-eyebrow">AGENTIC WORKFLOW</span>
            {isDemoPlan && (
              <span
                className="simulated-workflow-pill"
                role="status"
                aria-label="Workflow execution type: Simulated demo"
              >
                SIMULATED WORKFLOW (MOCK)
              </span>
            )}
          </div>
          <h2 id="workflow-heading-active" className="card-title workflow-goal">
            {plan.goal}
          </h2>
        </div>

        <div className="card-header-badges">
          <span
            className={`safety-badge safety-${plan.overall_safety_level.toLowerCase()}`}
            title={`Safety Risk Level ${plan.overall_safety_level}`}
            aria-label={`Overall safety level: ${plan.overall_safety_level}`}
          >
            Level {plan.overall_safety_level}
          </span>
          <span
            className={`plan-status-badge status-${plan.status.toLowerCase()}`}
            role="status"
            aria-label={`Overall plan status: ${plan.status}`}
          >
            {plan.status.replace(/_/g, ' ')}
          </span>
          {onClearPlan && (
            <button
              type="button"
              className="clear-plan-btn"
              onClick={onClearPlan}
              aria-label="Dismiss workflow plan"
              title="Dismiss plan"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Progress Bar with Accessible Semantics */}
      <div className="workflow-progress-section">
        <div className="progress-meta">
          <span className="progress-label">
            Step {Math.min(plan.current_step_index + 1, totalSteps || 1)} of {totalSteps}
          </span>
          <span className="progress-percentage">{progressPercent}% Completed</span>
        </div>

        <div
          className="workflow-progress-track"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Workflow execution progress: ${progressPercent}% completed (${completedSteps} of ${totalSteps} steps completed)`}
        >
          <div
            className={`workflow-progress-fill ${plan.status.toLowerCase()}`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Step List with Semantic Ordered List */}
      <ol className="workflow-steps-list" aria-label="Workflow execution steps">
        {plan.steps.map((step) => {
          const isCurrent = step.step_number === plan.current_step_index + 1;
          return (
            <li
              key={step.id || `step-${step.step_number}`}
              className={`workflow-step-item step-status-${step.status} ${
                isCurrent ? 'is-current-step' : ''
              }`}
            >
              <div className="step-indicator-col">
                {renderStatusIcon(step.status)}
                <span className="step-number-text">{step.step_number}</span>
              </div>

              <div className="step-content-col">
                <div className="step-top-row">
                  <span className="step-description">{step.description}</span>
                  <div className="step-badges-group">
                    <code className="step-tool-name">{step.tool_name}</code>
                    <span
                      className={`step-status-pill pill-${step.status}`}
                      role="status"
                      aria-label={`Step ${step.step_number} status: ${step.status}`}
                    >
                      {step.status.toUpperCase()}
                    </span>
                  </div>
                </div>

                {/* Failed Error Message Callout */}
                {step.status === 'failed' && step.error && (
                  <div className="step-error-callout" role="alert">
                    <span className="error-title">Execution Error:</span> {step.error}
                  </div>
                )}

                {/* Rejected State Callout */}
                {step.status === 'rejected' && (
                  <div className="step-rejected-callout" role="note">
                    Action rejected by safety policy or operator; execution halted.
                  </div>
                )}

                {/* Cancelled State Callout */}
                {step.status === 'cancelled' && (
                  <div className="step-cancelled-callout" role="note">
                    Step execution was cancelled.
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>

      {/* Screen Reader Live Region for Announcements */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>
    </section>
  );
};
