import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkflowProgressCard } from '../components/WorkflowProgressCard';
import { ActionPlan } from '../types/workflow';

describe('WorkflowProgressCard Component', () => {
  it('renders standby state when no plan is active', () => {
    render(<WorkflowProgressCard plan={null} />);

    expect(screen.getByText('AGENTIC WORKFLOW')).toBeTruthy();
    expect(screen.getByText('IDLE')).toBeTruthy();
    expect(
      screen.getByText(/No active workflow plan. Spoken requests requiring multi-step tool execution/i)
    ).toBeTruthy();
  });

  it('renders simulated demo trigger button in mock mode and responds to clicks', () => {
    const handleTrigger = vi.fn();
    render(
      <WorkflowProgressCard
        plan={null}
        isMockMode={true}
        onTriggerDemoPlan={handleTrigger}
      />
    );

    expect(screen.getByText('SIMULATED TESTING')).toBeTruthy();
    const demoBtn = screen.getByRole('button', {
      name: /Load simulated demo workflow plan/i,
    });
    expect(demoBtn).toBeTruthy();

    fireEvent.click(demoBtn);
    expect(handleTrigger).toHaveBeenCalledTimes(1);
  });

  it('renders active workflow plan with goal, safety level, and plan status badge', () => {
    const mockPlan: ActionPlan = {
      plan_id: 'plan-123',
      session_id: 'session-456',
      goal: 'Find all PDF reports and summarize findings',
      steps: [
        {
          id: 'step-1',
          step_number: 1,
          description: 'Search filesystem for report PDFs',
          tool_name: 'file.search',
          safety_level: 'A',
          status: 'completed',
        },
      ],
      current_step_index: 0,
      overall_safety_level: 'B',
      requires_approval: false,
      status: 'EXECUTING',
      created_at: 1731670000,
    };

    render(<WorkflowProgressCard plan={mockPlan} />);

    expect(screen.getByText('Find all PDF reports and summarize findings')).toBeTruthy();
    expect(screen.getByText('Level B')).toBeTruthy();
    expect(screen.getByText('EXECUTING')).toBeTruthy();
    expect(screen.getByText('Step 1 of 1')).toBeTruthy();
    expect(screen.getByText('100% Completed')).toBeTruthy();
  });

  it('calculates progress accurately and handles empty step list safely', () => {
    const emptyPlan: ActionPlan = {
      plan_id: 'plan-empty',
      session_id: 'session-456',
      goal: 'Empty workflow goal',
      steps: [],
      current_step_index: 0,
      overall_safety_level: 'A',
      requires_approval: false,
      status: 'PLANNING',
      created_at: 1731670000,
    };

    const { rerender } = render(<WorkflowProgressCard plan={emptyPlan} />);

    const emptyProgressBar = screen.getByRole('progressbar');
    expect(emptyProgressBar.getAttribute('aria-valuenow')).toBe('0');
    expect(screen.getByText('0% Completed')).toBeTruthy();

    // Rerender with 2 of 4 steps completed (50%)
    const fourStepPlan: ActionPlan = {
      ...emptyPlan,
      steps: [
        {
          id: 's1',
          step_number: 1,
          description: 'Step 1',
          tool_name: 't1',
          safety_level: 'A',
          status: 'completed',
        },
        {
          id: 's2',
          step_number: 2,
          description: 'Step 2',
          tool_name: 't2',
          safety_level: 'A',
          status: 'completed',
        },
        {
          id: 's3',
          step_number: 3,
          description: 'Step 3',
          tool_name: 't3',
          safety_level: 'B',
          status: 'running',
        },
        {
          id: 's4',
          step_number: 4,
          description: 'Step 4',
          tool_name: 't4',
          safety_level: 'A',
          status: 'pending',
        },
      ],
      current_step_index: 2,
    };

    rerender(<WorkflowProgressCard plan={fourStepPlan} />);

    const updatedProgressBar = screen.getByRole('progressbar');
    expect(updatedProgressBar.getAttribute('aria-valuenow')).toBe('50');
    expect(screen.getByText('50% Completed')).toBeTruthy();
    expect(screen.getByText('Step 3 of 4')).toBeTruthy();
  });

  it('renders all 6 verified step status states (pending, running, completed, failed, rejected, cancelled)', () => {
    const multiStatePlan: ActionPlan = {
      plan_id: 'plan-all-states',
      session_id: 'session-456',
      goal: 'Test all six lifecycle states',
      steps: [
        {
          id: 's-pending',
          step_number: 1,
          description: 'Pending task item',
          tool_name: 'tool.queue',
          safety_level: 'A',
          status: 'pending',
        },
        {
          id: 's-running',
          step_number: 2,
          description: 'Currently running task item',
          tool_name: 'tool.exec',
          safety_level: 'B',
          status: 'running',
        },
        {
          id: 's-completed',
          step_number: 3,
          description: 'Successfully finished task item',
          tool_name: 'tool.done',
          safety_level: 'A',
          status: 'completed',
        },
        {
          id: 's-failed',
          step_number: 4,
          description: 'Failed step item',
          tool_name: 'tool.faulty',
          safety_level: 'B',
          status: 'failed',
          error: 'Connection timed out to remote service',
        },
        {
          id: 's-rejected',
          step_number: 5,
          description: 'Rejected step requiring approval',
          tool_name: 'tool.sensitive',
          safety_level: 'C',
          status: 'rejected',
        },
        {
          id: 's-cancelled',
          step_number: 6,
          description: 'Cancelled step item',
          tool_name: 'tool.aborted',
          safety_level: 'A',
          status: 'cancelled',
        },
      ],
      current_step_index: 1,
      overall_safety_level: 'C',
      requires_approval: true,
      status: 'EXECUTING',
      created_at: 1731670000,
    };

    render(<WorkflowProgressCard plan={multiStatePlan} />);

    // Check all badges
    expect(screen.getByText('PENDING')).toBeTruthy();
    expect(screen.getByText('RUNNING')).toBeTruthy();
    expect(screen.getByText('COMPLETED')).toBeTruthy();
    expect(screen.getByText('FAILED')).toBeTruthy();
    expect(screen.getByText('REJECTED')).toBeTruthy();
    expect(screen.getByText('CANCELLED')).toBeTruthy();

    // Check descriptions
    expect(screen.getByText('Pending task item')).toBeTruthy();
    expect(screen.getByText('Currently running task item')).toBeTruthy();
    expect(screen.getByText('Successfully finished task item')).toBeTruthy();
    expect(screen.getByText('Failed step item')).toBeTruthy();
    expect(screen.getByText('Rejected step requiring approval')).toBeTruthy();
    expect(screen.getByText('Cancelled step item')).toBeTruthy();

    // Check error message callout for failed step
    const alertCallout = screen.getByRole('alert');
    expect(alertCallout.textContent).toContain('Connection timed out to remote service');

    // Check callouts for rejected and cancelled
    expect(
      screen.getByText(/Action rejected by safety policy or operator/i)
    ).toBeTruthy();
    expect(screen.getByText(/Step execution was cancelled/i)).toBeTruthy();
  });

  it('renders simulated mock demo badge when isDemoPlan is true', () => {
    const mockPlan: ActionPlan = {
      plan_id: 'plan-mock-1',
      session_id: 'session-456',
      goal: 'Simulated demo workflow',
      steps: [],
      current_step_index: 0,
      overall_safety_level: 'B',
      requires_approval: false,
      status: 'EXECUTING',
      created_at: 1731670000,
    };

    render(<WorkflowProgressCard plan={mockPlan} isDemoPlan={true} />);

    const mockPill = screen.getByRole('status', {
      name: /Workflow execution type: Simulated demo/i,
    });
    expect(mockPill).toBeTruthy();
    expect(mockPill.textContent).toContain('SIMULATED WORKFLOW (MOCK)');
  });

  it('delivers accessible screen reader announcements on state transitions', () => {
    const planA: ActionPlan = {
      plan_id: 'plan-announce',
      session_id: 'session-456',
      goal: 'Initial announcement goal',
      steps: [
        {
          id: 'step-1',
          step_number: 1,
          description: 'First action',
          tool_name: 'tool.one',
          safety_level: 'A',
          status: 'running',
        },
      ],
      current_step_index: 0,
      overall_safety_level: 'A',
      requires_approval: false,
      status: 'EXECUTING',
      created_at: 1731670000,
    };

    const { rerender } = render(<WorkflowProgressCard plan={planA} />);

    const liveRegion = screen.getByText(/Workflow step 1 running: First action/i);
    expect(liveRegion).toBeTruthy();

    // Transition step to completed
    const planB: ActionPlan = {
      ...planA,
      status: 'COMPLETED',
      steps: [
        {
          ...planA.steps[0],
          status: 'completed',
        },
      ],
    };

    rerender(<WorkflowProgressCard plan={planB} />);

    expect(
      screen.getByText(/Workflow completed successfully: Initial announcement goal/i)
    ).toBeTruthy();
  });

  it('allows dismissing workflow plan via clear button', () => {
    const handleClear = vi.fn();
    const mockPlan: ActionPlan = {
      plan_id: 'plan-clearable',
      session_id: 'session-456',
      goal: 'Clearable goal',
      steps: [],
      current_step_index: 0,
      overall_safety_level: 'A',
      requires_approval: false,
      status: 'COMPLETED',
      created_at: 1731670000,
    };

    render(<WorkflowProgressCard plan={mockPlan} onClearPlan={handleClear} />);

    const clearBtn = screen.getByRole('button', { name: 'Dismiss workflow plan' });
    fireEvent.click(clearBtn);

    expect(handleClear).toHaveBeenCalledTimes(1);
  });
});
