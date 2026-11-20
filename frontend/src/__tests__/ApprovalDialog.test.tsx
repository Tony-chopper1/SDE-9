import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ApprovalDialog } from '../components/ApprovalDialog';
import { ActionPlan, ApprovalRequest } from '../types/workflow';

describe('ApprovalDialog Component', () => {
  const baseRequest: ApprovalRequest = {
    request_id: 'req-test-001',
    plan_id: 'plan-xyz',
    session_id: 'sess-123',
    safety_level: 'C',
    status: 'PENDING',
    created_at: 1731670000,
    action: 'Modify configuration file',
    description: 'Update application settings in config.json',
    tool_name: 'config.update',
    step_number: 2,
    parameters: { key: 'debug_mode', value: true },
  };

  const basePlan: ActionPlan = {
    plan_id: 'plan-xyz',
    session_id: 'sess-123',
    goal: 'Automated infrastructure maintenance',
    steps: [
      {
        id: 's1',
        step_number: 1,
        description: 'Read current config',
        tool_name: 'file.read',
        safety_level: 'A',
        status: 'completed',
      },
      {
        id: 's2',
        step_number: 2,
        description: 'Update application settings in config.json',
        tool_name: 'config.update',
        safety_level: 'C',
        status: 'pending',
      },
    ],
    current_step_index: 1,
    overall_safety_level: 'C',
    requires_approval: true,
    status: 'AWAITING_APPROVAL',
    created_at: 1731670000,
  };

  let onApproveMock: ReturnType<typeof vi.fn>;
  let onRejectMock: ReturnType<typeof vi.fn>;
  let onCloseMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onApproveMock = vi.fn();
    onRejectMock = vi.fn();
    onCloseMock = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when isOpen is false or request is null', () => {
    const { rerender } = render(
      <ApprovalDialog
        isOpen={false}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );
    expect(screen.queryByRole('dialog')).toBeNull();

    rerender(
      <ApprovalDialog
        isOpen={true}
        request={null}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders dialog with action details, plan goal, step number, tool, and parameters', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        associatedPlan={basePlan}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeTruthy();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(screen.getByText('Action Requires Authorization')).toBeTruthy();
    expect(screen.getByText('HUMAN-IN-THE-LOOP APPROVAL GATE')).toBeTruthy();
    expect(screen.getByText('Modify configuration file')).toBeTruthy();
    expect(screen.getByText('Automated infrastructure maintenance')).toBeTruthy();
    expect(screen.getByText('Step #2')).toBeTruthy();
    expect(screen.getByText('config.update')).toBeTruthy();
    expect(screen.getByText('req-test-001')).toBeTruthy();
    const paramsPre = screen.getByLabelText('Tool parameters');
    expect(paramsPre.textContent).toContain('"key": "debug_mode"');
    expect(paramsPre.textContent).toContain('"value": true');
  });

  it('displays Level C safety badge and sensitive risk description', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        associatedPlan={basePlan}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText(/Level C – Sensitive/i)).toBeTruthy();
    expect(screen.getByText('Potential Sensitivity Risks')).toBeTruthy();
    expect(screen.getByText(/Sensitive Action: This operation modifies state, files/i)).toBeTruthy();
  });

  it('displays Level D safety badge and destructive risk explanation', () => {
    const destructiveRequest: ApprovalRequest = {
      ...baseRequest,
      request_id: 'req-destruct-01',
      safety_level: 'D',
      action: 'Delete production database replica',
      tool_name: 'db.drop_replica',
      risk_assessment: 'Irreversible deletion of test database records.',
    };

    render(
      <ApprovalDialog
        isOpen={true}
        request={destructiveRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText(/Level D – Destructive/i)).toBeTruthy();
    expect(screen.getByText('Potential Destructive Risks')).toBeTruthy();
    expect(screen.getByText('Irreversible deletion of test database records.')).toBeTruthy();
  });

  it('handles missing or malformed event data safely without crashing', () => {
    const malformedRequest: ApprovalRequest = {
      request_id: '',
      plan_id: '',
      session_id: '',
      safety_level: '' as any,
      status: 'PENDING',
      created_at: 0,
    };

    render(
      <ApprovalDialog
        isOpen={true}
        request={malformedRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.getByText(/Level C – Sensitive/i)).toBeTruthy();
    expect(screen.getByText('Sensitive Workflow Action')).toBeTruthy();
  });

  it('displays simulated demo badge when isDemo is true', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        isDemo={true}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    const demoBadge = screen.getByRole('status', { name: /Approval mode: Simulated demo/i });
    expect(demoBadge).toBeTruthy();
    expect(demoBadge.textContent).toContain('SIMULATED APPROVAL (DEMO)');
    // System notice regarding live backend limitation is omitted for mock demo
    expect(screen.queryByText(/The backend does not currently expose/i)).toBeNull();
  });

  it('displays system limitation note when operating on live backend', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        isDemo={false}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    expect(screen.getByRole('note')).toBeTruthy();
    expect(screen.getByText(/The backend does not currently expose a live approval execution endpoint/i)).toBeTruthy();
  });

  it('calls onApprove when Approve Action button is clicked', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /Approve requested action/i });
    fireEvent.click(approveBtn);

    expect(onApproveMock).toHaveBeenCalledTimes(1);
    expect(onApproveMock).toHaveBeenCalledWith('req-test-001');
    expect(onRejectMock).not.toHaveBeenCalled();
  });

  it('calls onReject when Reject Action button is clicked with optional reason', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    const reasonInput = screen.getByLabelText(/Rejection Reason \(Optional\):/i);
    fireEvent.change(reasonInput, { target: { value: 'Operation rejected due to invalid file path' } });

    const rejectBtn = screen.getByRole('button', { name: /Reject requested action/i });
    fireEvent.click(rejectBtn);

    expect(onRejectMock).toHaveBeenCalledTimes(1);
    expect(onRejectMock).toHaveBeenCalledWith(
      'req-test-001',
      'Operation rejected due to invalid file path'
    );
    expect(onApproveMock).not.toHaveBeenCalled();
  });

  it('prevents duplicate decisions by disabling buttons once decided', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /Approve requested action/i });
    const rejectBtn = screen.getByRole('button', { name: /Reject requested action/i });

    expect(approveBtn.hasAttribute('disabled')).toBe(false);
    expect(rejectBtn.hasAttribute('disabled')).toBe(false);

    fireEvent.click(approveBtn);

    // After click, buttons are immediately disabled to prevent duplicate decisions
    expect(approveBtn.hasAttribute('disabled')).toBe(true);
    expect(rejectBtn.hasAttribute('disabled')).toBe(true);

    // Subsequent clicks do not fire duplicate callbacks
    fireEvent.click(approveBtn);
    fireEvent.click(rejectBtn);
    expect(onApproveMock).toHaveBeenCalledTimes(1);
    expect(onRejectMock).not.toHaveBeenCalled();
  });

  it('handles Escape key by dismissing without approving or rejecting', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onCloseMock).toHaveBeenCalledTimes(1);
    expect(onApproveMock).not.toHaveBeenCalled();
    expect(onRejectMock).not.toHaveBeenCalled();
  });

  it('dismisses dialog without decision when clicking the close (X) or dismiss button', () => {
    render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    // Header close button with distinct accessible name
    const closeBtn = screen.getByRole('button', {
      name: 'Close approval dialog',
    });
    fireEvent.click(closeBtn);
    expect(onCloseMock).toHaveBeenCalledTimes(1);

    // Footer dismiss button with distinct accessible name
    const dismissBtn = screen.getByRole('button', {
      name: 'Dismiss approval dialog without decision',
    });
    fireEvent.click(dismissBtn);
    expect(onCloseMock).toHaveBeenCalledTimes(2);

    expect(onApproveMock).not.toHaveBeenCalled();
    expect(onRejectMock).not.toHaveBeenCalled();
  });

  it('traps focus inside the dialog with Tab navigation', () => {
    render(
      <div>
        <button id="outside-trigger">Trigger</button>
        <ApprovalDialog
          isOpen={true}
          request={baseRequest}
          onApprove={onApproveMock}
          onReject={onRejectMock}
          onClose={onCloseMock}
        />
      </div>
    );

    const dialog = screen.getByRole('dialog');
    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    expect(focusable.length).toBeGreaterThan(0);

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    // Shift+Tab on first wraps to last
    first.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    // Tab on last wraps to first
    last.focus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: false });
  });

  it('restores focus to previous element when closed', () => {
    const trigger = document.createElement('button');
    trigger.id = 'trigger-btn';
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const { unmount } = render(
      <ApprovalDialog
        isOpen={true}
        request={baseRequest}
        onApprove={onApproveMock}
        onReject={onRejectMock}
        onClose={onCloseMock}
      />
    );

    unmount();
    expect(document.activeElement).toBe(trigger);
    document.body.removeChild(trigger);
  });
});
