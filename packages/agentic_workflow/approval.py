"""
Human-in-the-loop approval gate and TTL expiration management.

Manages approval requests for sensitive and destructive action plans,
enforces configurable TTL expiration, and implements strict authorization checks.
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Union

from packages.agentic_workflow.models import (
    ActionPlan,
    ApprovalRequest,
    ApprovalStatus,
    PlanStatus,
    SafetyLevel,
    WorkflowPlan,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ApprovalError(Exception):
    """Base exception for approval management errors."""


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request cannot be located by ID."""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(f"Approval request '{request_id}' not found.")


class ApprovalExpiredError(ApprovalError):
    """Raised when attempting an action on an expired approval request."""

    def __init__(self, request_id: str) -> None:
        self.request_id = request_id
        super().__init__(f"Approval request '{request_id}' has expired.")


# ---------------------------------------------------------------------------
# Approval Manager
# ---------------------------------------------------------------------------


class ApprovalManager:
    """Manages creation, decision recording, TTL expiry, and execution gating.

    Rules:
        * Low-risk plans (requires_approval=False) are permitted automatically.
        * Sensitive / destructive plans (requires_approval=True) MUST be explicitly
          approved before tool execution is allowed.
        * Any plan whose approval request is PENDING, REJECTED, or EXPIRED is
          STRICTLY forbidden from executing tools.
    """

    def __init__(self, default_ttl_seconds: float = 300.0) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._requests: Dict[str, ApprovalRequest] = {}
        self._plan_to_request_id: Dict[str, str] = {}

    def create_request(
        self,
        plan_id: str,
        session_id: str,
        safety_level: SafetyLevel,
        ttl_seconds: Optional[float] = None,
    ) -> ApprovalRequest:
        """Create and register a pending approval request with optional TTL.

        Args:
            plan_id: The ID of the action plan requiring approval.
            session_id: Session identifier.
            safety_level: Severity triggering the gate (C or D).
            ttl_seconds: Time-to-live in seconds, or None for no expiration.
                         Defaults to `self.default_ttl_seconds`.

        Returns:
            The created :class:`ApprovalRequest`.
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = time.time()
        expires_at = (now + ttl) if (ttl is not None and ttl > 0) else None

        req = ApprovalRequest(
            plan_id=plan_id,
            session_id=session_id,
            safety_level=safety_level,
            status=ApprovalStatus.PENDING,
            expires_at=expires_at,
            created_at=now,
        )
        self._requests[req.request_id] = req
        self._plan_to_request_id[plan_id] = req.request_id
        return req

    def get_request(self, request_id: str) -> ApprovalRequest:
        """Retrieve an approval request by ID, evaluating TTL expiration."""
        if request_id not in self._requests:
            raise ApprovalNotFoundError(request_id)

        req = self._requests[request_id]
        self._check_and_update_expiry(req)
        return req

    def get_request_for_plan(self, plan_id: str) -> Optional[ApprovalRequest]:
        """Retrieve the active approval request associated with *plan_id*, if any."""
        req_id = self._plan_to_request_id.get(plan_id)
        if req_id is None:
            return None
        return self.get_request(req_id)

    def _check_and_update_expiry(self, req: ApprovalRequest) -> None:
        """Mark *req* as EXPIRED if its TTL has elapsed."""
        if (
            req.status == ApprovalStatus.PENDING
            and req.expires_at is not None
            and time.time() > req.expires_at
        ):
            req.status = ApprovalStatus.EXPIRED

    def approve(
        self,
        request_id: str,
        decided_by: str = "operator",
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """Approve an active pending request.

        Raises:
            ApprovalNotFoundError: If *request_id* is unknown.
            ApprovalExpiredError: If the request has passed its TTL.
            ApprovalError: If the request was already rejected.
        """
        req = self.get_request(request_id)

        if req.status == ApprovalStatus.EXPIRED:
            raise ApprovalExpiredError(request_id)
        if req.status == ApprovalStatus.REJECTED:
            raise ApprovalError(f"Cannot approve already-rejected request '{request_id}'.")

        now = time.time()
        req.status = ApprovalStatus.APPROVED
        req.decided_at = now
        req.decided_by = decided_by
        req.reason = reason
        return req

    def reject(
        self,
        request_id: str,
        decided_by: str = "operator",
        reason: Optional[str] = None,
    ) -> ApprovalRequest:
        """Reject an approval request."""
        req = self.get_request(request_id)
        now = time.time()
        req.status = ApprovalStatus.REJECTED
        req.decided_at = now
        req.decided_by = decided_by
        req.reason = reason
        return req

    def expire(self, request_id: str) -> ApprovalRequest:
        """Explicitly transition an approval request to EXPIRED."""
        req = self.get_request(request_id)
        req.status = ApprovalStatus.EXPIRED
        return req

    def check_expiry(self, request_id: str) -> ApprovalStatus:
        """Evaluate and return the up-to-date :class:`ApprovalStatus` for *request_id*."""
        req = self.get_request(request_id)
        return req.status

    # ------------------------------------------------------------------
    # Non-negotiable Execution Safety Gate
    # ------------------------------------------------------------------

    def is_execution_permitted(
        self, plan: Union[ActionPlan, WorkflowPlan]
    ) -> bool:
        """Determine whether execution of *plan* is strictly permitted.

        Non-negotiable rule:
            * If `requires_approval` is False, returns True.
            * If `requires_approval` is True, returns True ONLY IF the plan was
              explicitly approved and has not expired.
            * A rejected, expired, or pending plan must strictly NEVER execute any tools.

        Args:
            plan: The :class:`ActionPlan` to verify.

        Returns:
            ``True`` if permitted, ``False`` if blocked by approval gate.
        """
        # If low-risk informational plan, auto-permitted
        if not plan.requires_approval:
            return True

        # Check registered request in manager
        req = self.get_request_for_plan(plan.plan_id)
        if req is not None:
            self._check_and_update_expiry(req)
            if req.status == ApprovalStatus.APPROVED:
                # Double-check that approval did not expire
                if req.expires_at is not None and time.time() > req.expires_at:
                    req.status = ApprovalStatus.EXPIRED
                    return False
                return True
            # In all other states (PENDING, REJECTED, EXPIRED), strictly block
            return False

        # Fallback to plan-level metadata (if approved via sm.approve_plan without manager)
        if plan.rejected_at is not None or plan.status == PlanStatus.REJECTED:
            return False

        if plan.status == PlanStatus.EXPIRED:
            return False

        if plan.approved_at is not None:
            return True

        return False
