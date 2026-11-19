import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { ActionPlan, ApprovalRequest, SafetyLevel } from '../types/workflow';

export interface ApprovalDialogProps {
  isOpen: boolean;
  request: ApprovalRequest | null;
  associatedPlan?: ActionPlan | null;
  isDemo?: boolean;
  onApprove: (requestId: string, reason?: string) => void;
  onReject: (requestId: string, reason?: string) => void;
  onClose: () => void;
  isProcessing?: boolean;
}

export const ApprovalDialog: React.FC<ApprovalDialogProps> = ({
  isOpen,
  request,
  associatedPlan,
  isDemo = false,
  onApprove,
  onReject,
  onClose,
  isProcessing = false,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const lastActiveElementRef = useRef<HTMLElement | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string>('');
  const [decisionMade, setDecisionMade] = useState<'APPROVED' | 'REJECTED' | null>(null);

  // Derive safety level with safe fallback to 'C'
  const safetyLevel: SafetyLevel = useMemo(() => {
    if (!request || !request.safety_level) return 'C';
    const lvl = String(request.safety_level).toUpperCase();
    if (lvl === 'D') return 'D';
    if (lvl === 'B') return 'B';
    if (lvl === 'A') return 'A';
    return 'C';
  }, [request]);

  // Derived action title and description with safe fallbacks
  const actionTitle = useMemo(() => {
    if (!request) return 'Workflow Action';
    return (
      request.action ||
      request.description ||
      (request.tool_name ? `Execute ${request.tool_name}` : 'Sensitive Workflow Action')
    );
  }, [request]);

  const toolName = useMemo(() => {
    if (request?.tool_name) return request.tool_name;
    if (associatedPlan && typeof request?.step_number === 'number') {
      const step = associatedPlan.steps.find((s) => s.step_number === request.step_number);
      if (step?.tool_name) return step.tool_name;
    }
    return null;
  }, [request, associatedPlan]);

  // Derive risk explanation based on safety level and tool
  const riskExplanation = useMemo(() => {
    if (request?.risk_assessment) {
      return request.risk_assessment;
    }
    if (request?.risks && request.risks.length > 0) {
      return request.risks.join('; ');
    }
    if (safetyLevel === 'D') {
      return 'Destructive Action: This operation carries high risk of irreversible changes. It may permanently delete workspace files, overwrite configuration, or perform privileged operations. Proceed with extreme caution.';
    }
    return 'Sensitive Action: This operation modifies state, files, or external services. Ensure that the parameters and target paths are correct before granting permission.';
  }, [request, safetyLevel]);

  // Reset state whenever a new request arrives or dialog opens
  useEffect(() => {
    if (isOpen) {
      setDecisionMade(null);
      setRejectionReason('');
    }
  }, [isOpen, request?.request_id]);

  // Accessibility: Focus management and focus trapping
  useEffect(() => {
    if (!isOpen) return;

    // Save currently focused element to restore later
    lastActiveElementRef.current = document.activeElement as HTMLElement | null;

    // Focus the reject button or dialog container on open
    const focusTimer = setTimeout(() => {
      if (dialogRef.current) {
        const rejectBtn = dialogRef.current.querySelector<HTMLButtonElement>(
          '.approval-btn-reject'
        );
        if (rejectBtn) {
          rejectBtn.focus();
        } else {
          dialogRef.current.focus();
        }
      }
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape key handles dismissal safely WITHOUT approving or rejecting
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      // Tab key focus trap
      if (e.key === 'Tab' && dialogRef.current) {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        const focusable = Array.from(focusableElements);
        if (focusable.length === 0) return;

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      clearTimeout(focusTimer);
      window.removeEventListener('keydown', handleKeyDown);
      // Restore focus to previous trigger
      if (lastActiveElementRef.current && typeof lastActiveElementRef.current.focus === 'function') {
        lastActiveElementRef.current.focus();
      }
    };
  }, [isOpen, onClose]);

  const handleApprove = useCallback(() => {
    if (!request || decisionMade || isProcessing) return;
    setDecisionMade('APPROVED');
    onApprove(request.request_id);
  }, [request, decisionMade, isProcessing, onApprove]);

  const handleReject = useCallback(() => {
    if (!request || decisionMade || isProcessing) return;
    setDecisionMade('REJECTED');
    onReject(request.request_id, rejectionReason.trim() || undefined);
  }, [request, decisionMade, isProcessing, onReject, rejectionReason]);

  if (!isOpen || !request) {
    return null;
  }

  const isDecided = decisionMade !== null || request.status === 'APPROVED' || request.status === 'REJECTED';

  return (
    <div
      className="approval-dialog-backdrop"
      role="presentation"
      onClick={(e) => {
        // Clicking backdrop dismisses dialog safely without deciding
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="approval-dialog-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="approval-dialog-title"
        aria-describedby="approval-dialog-description"
        ref={dialogRef}
        tabIndex={-1}
      >
        {/* Header */}
        <div className="approval-dialog-header">
          <div className="approval-header-titles">
            <div className="approval-eyebrow-row">
              <span className="approval-eyebrow">HUMAN-IN-THE-LOOP APPROVAL GATE</span>
              {isDemo && (
                <span
                  className="simulated-workflow-pill"
                  role="status"
                  aria-label="Approval mode: Simulated demo"
                >
                  SIMULATED APPROVAL (DEMO)
                </span>
              )}
            </div>
            <h2 id="approval-dialog-title" className="approval-dialog-title">
              Action Requires Authorization
            </h2>
          </div>
          <button
            type="button"
            className="approval-close-btn"
            onClick={onClose}
            aria-label="Close approval dialog"
            title="Dismiss dialog (leaves request pending)"
          >
            ✕
          </button>
        </div>

        {/* Body Content */}
        <div className="approval-dialog-body" id="approval-dialog-description">
          {/* Action and Safety Summary Box */}
          <div className="approval-action-card">
            <div className="approval-action-header">
              <div className="approval-action-name-group">
                <span className="approval-label">REQUESTED ACTION</span>
                <p className="approval-action-text">{actionTitle}</p>
              </div>
              <span
                className={`safety-badge safety-${safetyLevel.toLowerCase()} safety-badge-lg`}
                role="status"
                aria-label={`Safety level: Level ${safetyLevel}`}
              >
                Level {safetyLevel} – {safetyLevel === 'D' ? 'Destructive' : 'Sensitive'}
              </span>
            </div>

            {/* Context details */}
            <div className="approval-details-grid">
              {associatedPlan && (
                <div className="approval-detail-item">
                  <span className="detail-label">Associated Goal:</span>
                  <span className="detail-value">{associatedPlan.goal}</span>
                </div>
              )}
              {typeof request.step_number === 'number' && (
                <div className="approval-detail-item">
                  <span className="detail-label">Workflow Step:</span>
                  <span className="detail-value">Step #{request.step_number}</span>
                </div>
              )}
              {toolName && (
                <div className="approval-detail-item">
                  <span className="detail-label">Tool Identifier:</span>
                  <code className="detail-code">{toolName}</code>
                </div>
              )}
              {request.request_id && (
                <div className="approval-detail-item">
                  <span className="detail-label">Request ID:</span>
                  <span className="detail-value-mono">{request.request_id}</span>
                </div>
              )}
            </div>

            {/* Parameters preview if present */}
            {request.parameters && Object.keys(request.parameters).length > 0 && (
              <div className="approval-params-box">
                <span className="params-label">Invocation Parameters:</span>
                <pre className="params-code" tabIndex={0} aria-label="Tool parameters">
                  {JSON.stringify(request.parameters, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Risk Information Callout */}
          <div
            className={`approval-risk-callout risk-level-${safetyLevel.toLowerCase()}`}
            role="alert"
          >
            <div className="risk-icon" aria-hidden="true">
              {safetyLevel === 'D' ? '⚠️' : 'ℹ️'}
            </div>
            <div className="risk-content">
              <h3 className="risk-heading">
                {safetyLevel === 'D' ? 'Potential Destructive Risks' : 'Potential Sensitivity Risks'}
              </h3>
              <p className="risk-body-text">{riskExplanation}</p>
            </div>
          </div>

          {/* Backend Capability Limitation Note */}
          {!isDemo && (
            <div className="approval-limitation-note" role="note">
              <span className="limitation-label">System Notice:</span> The backend does not currently
              expose a live approval execution endpoint. Rejecting strictly guarantees execution will
              halt. Approving records your authorized sign-off in the session state.
            </div>
          )}

          {/* Decision Status Announcement */}
          {isDecided && (
            <div
              className={`approval-decision-banner decision-${(decisionMade || request.status).toLowerCase()}`}
              role="status"
              aria-live="polite"
            >
              {decisionMade === 'REJECTED' || request.status === 'REJECTED' ? (
                <span>
                  <strong>Action Rejected:</strong> Workflow execution is halted safely. No actions were
                  executed.
                </span>
              ) : (
                <span>
                  <strong>Action Approved:</strong> Authorization has been recorded.
                </span>
              )}
            </div>
          )}

          {/* Optional Rejection Reason Input when pending */}
          {!isDecided && (
            <div className="approval-reason-field">
              <label htmlFor="approval-reason-input" className="reason-label">
                Rejection Reason (Optional):
              </label>
              <input
                id="approval-reason-input"
                type="text"
                className="reason-input"
                placeholder="e.g., Unintended target directory or invalid parameter"
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                disabled={isDecided || isProcessing}
                maxLength={200}
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="approval-dialog-footer">
          <button
            type="button"
            className="approval-btn approval-btn-dismiss"
            onClick={onClose}
            aria-label="Dismiss approval dialog without decision"
          >
            Dismiss
          </button>

          <div className="approval-decision-buttons">
            <button
              type="button"
              className="approval-btn approval-btn-reject"
              onClick={handleReject}
              disabled={isDecided || isProcessing}
              aria-label="Reject requested action and halt execution"
            >
              ✕ Reject Action
            </button>
            <button
              type="button"
              className="approval-btn approval-btn-approve"
              onClick={handleApprove}
              disabled={isDecided || isProcessing}
              aria-label="Approve requested action"
            >
              ✓ Approve Action
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
