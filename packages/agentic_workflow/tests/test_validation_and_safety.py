"""
Unit and integration tests for Week 2 Agentic Workflow deliverables.

Covers:
    * DAG cycle detection via DFS coloring and missing prerequisite dependencies.
    * Prerequisite topological execution ordering.
    * ToolRegistry allow-listing, parameter schema validation, and permission scopes.
    * ApprovalManager lifecycle, TTL expiration, and non-negotiable execution gating.
    * Safe audit event recording (step ID, decision, reason, timestamp, strictly NO sensitive args)
      for approve, reject, and expiry.
    * Verifications that rejected or expired approvals run ZERO tools and write the audit event.
    * MockToolExecutor timeouts, bounded retries for idempotent tools, retry suppression
      for non-idempotent tools, and cancellation.
    * State machine execute_plan integration with topological execution and approval checks.
"""

from __future__ import annotations

import time
import pytest

from packages.agentic_workflow.approval import (
    ApprovalError,
    ApprovalExpiredError,
    ApprovalManager,
    ApprovalNotFoundError,
)
from packages.agentic_workflow.mock_executor import (
    MockToolExecutor,
)
from packages.agentic_workflow.models import (
    ActionPlan,
    AgentState,
    ApprovalStatus,
    AuditEvent,
    PermissionScope,
    PlanStatus,
    SafetyLevel,
    WorkflowStep,
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
)
from packages.agentic_workflow.validator import (
    CircularDependencyError,
    MissingDependencyError,
    PlanValidationError,
    PlanValidator,
)


# ===========================================================================
# Helper Factories
# ===========================================================================


def _step(
    step_id: str,
    tool_name: str = "file.search",
    safety_level: SafetyLevel = SafetyLevel.A,
    depends_on: list[str] | None = None,
    parameters: dict | None = None,
    step_number: int = 1,
    is_idempotent: bool = True,
    timeout_seconds: float | None = None,
) -> WorkflowStep:
    return WorkflowStep(
        id=step_id,
        step_number=step_number,
        description=f"Description for {step_id}",
        tool_name=tool_name,
        safety_level=safety_level,
        depends_on=depends_on or [],
        parameters=parameters or {},
        is_idempotent=is_idempotent,
        timeout_seconds=timeout_seconds,
    )


# ===========================================================================
# 1. Plan Validation & DAG Dependency Analysis Tests
# ===========================================================================


class TestPlanValidatorDAG:
    def test_valid_linear_dag(self):
        s1 = _step("step-1", step_number=1)
        s2 = _step("step-2", step_number=2, depends_on=["step-1"])
        s3 = _step("step-3", step_number=3, depends_on=["step-2"])
        steps = [s1, s2, s3]

        assert PlanValidator.validate(steps) is True
        order = PlanValidator.get_topological_order(steps)
        assert order == ["step-1", "step-2", "step-3"]

    def test_valid_diamond_dag(self):
        # A -> B, A -> C, B -> D, C -> D
        s_a = _step("A", step_number=1)
        s_b = _step("B", step_number=2, depends_on=["A"])
        s_c = _step("C", step_number=3, depends_on=["A"])
        s_d = _step("D", step_number=4, depends_on=["B", "C"])
        steps = [s_a, s_b, s_c, s_d]

        assert PlanValidator.validate(steps) is True
        order = PlanValidator.get_topological_order(steps)
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order[1:3]) == {"B", "C"}

    def test_missing_dependency_raises(self):
        s1 = _step("step-1", depends_on=["non-existent-id"])
        with pytest.raises(MissingDependencyError) as exc_info:
            PlanValidator.validate([s1])
        assert exc_info.value.step_id == "step-1"
        assert exc_info.value.missing_dep == "non-existent-id"

    def test_self_dependency_raises_circular_error(self):
        s1 = _step("step-1", depends_on=["step-1"])
        with pytest.raises(CircularDependencyError) as exc_info:
            PlanValidator.validate([s1])
        assert "step-1 -> step-1" in str(exc_info.value)

    def test_two_node_circular_dependency(self):
        # A -> B -> A
        s_a = _step("step-A", depends_on=["step-B"])
        s_b = _step("step-B", depends_on=["step-A"])
        with pytest.raises(CircularDependencyError) as exc_info:
            PlanValidator.validate([s_a, s_b])
        assert "Circular dependency detected" in str(exc_info.value)
        assert len(exc_info.value.cycle_path) >= 2

    def test_multi_node_circular_dependency(self):
        # 1 -> 2 -> 3 -> 1
        s1 = _step("1", depends_on=["3"])
        s2 = _step("2", depends_on=["1"])
        s3 = _step("3", depends_on=["2"])
        with pytest.raises(CircularDependencyError) as exc_info:
            PlanValidator.validate([s1, s2, s3])
        assert "Circular dependency detected" in str(exc_info.value)

    def test_duplicate_step_id_raises_validation_error(self):
        s1 = _step("duplicate-id")
        s2 = _step("duplicate-id")
        with pytest.raises(PlanValidationError):
            PlanValidator.validate([s1, s2])

    def test_empty_steps_valid(self):
        assert PlanValidator.validate([]) is True
        assert PlanValidator.get_topological_order([]) == []

    def test_build_plan_validates_dag_by_default(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        s1 = _step("A", depends_on=["B"])
        s2 = _step("B", depends_on=["A"])
        with pytest.raises(CircularDependencyError):
            sm.build_plan("sess-1", "cyclic plan", [s1, s2])

    def test_build_plan_can_skip_validation_if_requested(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        s1 = _step("A", depends_on=["B"])
        # Validation skipped
        plan = sm.build_plan("sess-1", "unvalidated", [s1], validate=False)
        assert plan is not None


# ===========================================================================
# 2. Tool Registry & Permission Scopes Tests
# ===========================================================================


class TestToolRegistry:
    def test_default_tools_registered(self):
        reg = ToolRegistry()
        tools = reg.list_tools()
        assert "file.search" in tools
        assert "file.move" in tools
        assert "calc.evaluate" in tools

    def test_unregistered_tool_lookup_raises(self):
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get_spec("unauthorized.tool")

    def test_custom_tool_registration_and_removal(self):
        reg = ToolRegistry()
        custom = ToolSpec(
            name="custom.ping",
            permission_scope=PermissionScope.READ_ONLY,
            is_idempotent=True,
            safety_level=SafetyLevel.A,
        )
        reg.register(custom)
        assert reg.is_registered("custom.ping")
        assert reg.get_spec("custom.ping").name == "custom.ping"

        reg.unregister("custom.ping")
        assert not reg.is_registered("custom.ping")

    def test_file_move_parameter_validation(self):
        reg = ToolRegistry()
        # Missing source
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("file.move", {"destination": "/b.txt"})

        # Missing destination
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("file.move", {"source": "/a.txt"})

        # Empty string source
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("file.move", {"source": "  ", "destination": "/b.txt"})

        # Invalid type for overwrite
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("file.move", {
                "source": "/a.txt", "destination": "/b.txt", "overwrite": "not-a-bool"
            })

        # Valid parameters pass without exception
        reg.validate_parameters("file.move", {
            "source": "/a.txt", "destination": "/b.txt", "overwrite": True
        })

    def test_calc_evaluate_parameter_validation(self):
        reg = ToolRegistry()
        # Missing expression
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("calc.evaluate", {})

        # Empty expression
        with pytest.raises(ToolParameterError):
            reg.validate_parameters("calc.evaluate", {"expression": ""})

        # Valid expression
        reg.validate_parameters("calc.evaluate", {"expression": "2 + 2"})

    def test_permission_scope_hierarchy(self):
        reg = ToolRegistry()

        # READ_ONLY allows file.search and calc.evaluate, blocks file.move
        assert reg.check_permission("file.search", [PermissionScope.READ_ONLY]) is True
        assert reg.check_permission("calc.evaluate", [PermissionScope.READ_ONLY]) is True
        assert reg.check_permission("file.move", [PermissionScope.READ_ONLY]) is False

        # WORKSPACE_WRITE satisfies both WRITE and READ_ONLY
        assert reg.check_permission("file.move", [PermissionScope.WORKSPACE_WRITE]) is True
        assert reg.check_permission("file.search", [PermissionScope.WORKSPACE_WRITE]) is True

        # SYSTEM_EXEC satisfies everything
        assert reg.check_permission("file.move", [PermissionScope.SYSTEM_EXEC]) is True
        assert reg.check_permission("file.search", [PermissionScope.SYSTEM_EXEC]) is True

        # Insufficient scope raises PermissionDeniedError
        with pytest.raises(PermissionDeniedError):
            reg.enforce_permission("file.move", [PermissionScope.READ_ONLY])


# ===========================================================================
# 3. Approval Gate & TTL Expiry Tests
# ===========================================================================


class TestApprovalManager:
    def test_create_and_retrieve_request(self):
        mgr = ApprovalManager(default_ttl_seconds=60.0)
        req = mgr.create_request("plan-1", "sess-1", SafetyLevel.C)
        assert req.status == ApprovalStatus.PENDING
        assert req.expires_at is not None
        assert req.expires_at > time.time()

        retrieved = mgr.get_request(req.request_id)
        assert retrieved.request_id == req.request_id

    def test_approve_request(self):
        mgr = ApprovalManager()
        req = mgr.create_request("plan-1", "sess-1", SafetyLevel.D)
        approved = mgr.approve(req.request_id, decided_by="alice", reason="Looks safe")
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.decided_by == "alice"
        assert approved.reason == "Looks safe"

    def test_reject_request(self):
        mgr = ApprovalManager()
        req = mgr.create_request("plan-1", "sess-1", SafetyLevel.C)
        rejected = mgr.reject(req.request_id, decided_by="bob", reason="Too risky")
        assert rejected.status == ApprovalStatus.REJECTED
        assert rejected.reason == "Too risky"

    def test_cannot_approve_rejected_request(self):
        mgr = ApprovalManager()
        req = mgr.create_request("plan-1", "sess-1", SafetyLevel.C)
        mgr.reject(req.request_id)
        with pytest.raises(ApprovalError):
            mgr.approve(req.request_id)

    def test_ttl_expiry(self):
        mgr = ApprovalManager(default_ttl_seconds=0.01)
        req = mgr.create_request("plan-1", "sess-1", SafetyLevel.C, ttl_seconds=0.01)
        time.sleep(0.02)

        # Expiry is detected
        assert mgr.check_expiry(req.request_id) == ApprovalStatus.EXPIRED

        with pytest.raises(ApprovalExpiredError):
            mgr.approve(req.request_id)

    def test_unknown_request_raises(self):
        mgr = ApprovalManager()
        with pytest.raises(ApprovalNotFoundError):
            mgr.get_request("unknown-id")

    def test_is_execution_permitted_non_negotiable_rules(self):
        mgr = ApprovalManager()

        # 1. Informational / low-risk plan auto-permitted
        safe_plan = ActionPlan(session_id="s1", goal="read", requires_approval=False)
        assert mgr.is_execution_permitted(safe_plan) is True

        # 2. Sensitive plan with no approval: NOT permitted
        sensitive_plan = ActionPlan(session_id="s1", goal="delete", requires_approval=True)
        assert mgr.is_execution_permitted(sensitive_plan) is False

        # 3. Create request and verify pending: NOT permitted
        req = mgr.create_request(sensitive_plan.plan_id, "s1", SafetyLevel.D, ttl_seconds=300)
        assert mgr.is_execution_permitted(sensitive_plan) is False

        # 4. Reject request: STRICTLY NOT permitted
        mgr.reject(req.request_id, reason="Denied")
        assert mgr.is_execution_permitted(sensitive_plan) is False

        # 5. Create fresh request and approve: PERMITTED
        req2 = mgr.create_request(sensitive_plan.plan_id, "s1", SafetyLevel.D, ttl_seconds=300)
        mgr.approve(req2.request_id)
        assert mgr.is_execution_permitted(sensitive_plan) is True

        # 6. Once expired: STRICTLY NOT permitted
        req2.expires_at = time.time() - 10
        assert mgr.is_execution_permitted(sensitive_plan) is False


# ===========================================================================
# 4. Safe Audit Trail & Zero Tool Invocations Tests (Mentor Week 2 Feedback)
# ===========================================================================


class TestApprovalAuditTrail:
    """Verifies that approve, reject, and expiry record a safe audit event
    (step ID, decision, reason, timestamp, strictly NO sensitive arguments)
    and that rejected or expired approvals run ZERO tools."""

    def test_approve_writes_audit_event(self):
        mgr = ApprovalManager()
        req = mgr.create_request(
            plan_id="plan-audit-1",
            session_id="sess-1",
            safety_level=SafetyLevel.C,
            step_id="step-101",
        )
        before = time.time()
        mgr.approve(req.request_id, decided_by="admin", reason="Security review passed")
        after = time.time()

        trail = mgr.get_audit_trail()
        assert len(trail) == 1
        event = trail[0]

        assert isinstance(event, AuditEvent)
        assert event.step_id == "step-101"
        assert event.decision == "APPROVED"
        assert event.reason == "Security review passed"
        assert before <= event.timestamp <= after
        assert event.request_id == req.request_id
        assert event.plan_id == "plan-audit-1"

    def test_reject_writes_audit_event(self):
        mgr = ApprovalManager()
        req = mgr.create_request(
            plan_id="plan-audit-2",
            session_id="sess-2",
            safety_level=SafetyLevel.D,
            step_id="step-202",
        )
        before = time.time()
        mgr.reject(req.request_id, decided_by="secops", reason="Unauthorized destination path")
        after = time.time()

        trail = mgr.get_audit_trail()
        assert len(trail) == 1
        event = trail[0]

        assert isinstance(event, AuditEvent)
        assert event.step_id == "step-202"
        assert event.decision == "REJECTED"
        assert event.reason == "Unauthorized destination path"
        assert before <= event.timestamp <= after
        assert event.request_id == req.request_id
        assert event.plan_id == "plan-audit-2"

    def test_explicit_expire_writes_audit_event(self):
        mgr = ApprovalManager()
        req = mgr.create_request(
            plan_id="plan-audit-3",
            session_id="sess-3",
            safety_level=SafetyLevel.C,
            step_id="step-303",
        )
        before = time.time()
        mgr.expire(req.request_id, reason="Operator session timed out")
        after = time.time()

        trail = mgr.get_audit_trail()
        assert len(trail) == 1
        event = trail[0]

        assert isinstance(event, AuditEvent)
        assert event.step_id == "step-303"
        assert event.decision == "EXPIRED"
        assert event.reason == "Operator session timed out"
        assert before <= event.timestamp <= after
        assert event.request_id == req.request_id

    def test_ttl_expiry_automatically_writes_audit_event(self):
        mgr = ApprovalManager(default_ttl_seconds=0.01)
        req = mgr.create_request(
            plan_id="plan-audit-4",
            session_id="sess-4",
            safety_level=SafetyLevel.C,
            ttl_seconds=0.01,
            step_id="step-404",
        )
        assert len(mgr.get_audit_trail()) == 0

        # Wait for TTL to pass
        time.sleep(0.02)

        # Trigger check via check_expiry
        status = mgr.check_expiry(req.request_id)
        assert status == ApprovalStatus.EXPIRED

        trail = mgr.get_audit_trail()
        assert len(trail) == 1
        event = trail[0]
        assert event.step_id == "step-404"
        assert event.decision == "EXPIRED"
        assert "expired" in event.reason.lower()

    def test_audit_event_strictly_contains_no_sensitive_arguments(self):
        """Audit trail entries must contain step ID, decision, reason, timestamp,
        and strictly NO sensitive tool arguments or parameters."""
        mgr = ApprovalManager()
        req = mgr.create_request("p", "s", SafetyLevel.C, step_id="sensitive-step")
        mgr.reject(req.request_id, reason="Disallowed parameters")

        event = mgr.get_audit_trail()[0]
        event_dict = event.model_dump()

        # Verify only safe metadata fields exist
        allowed_fields = {"step_id", "decision", "reason", "timestamp", "request_id", "plan_id"}
        assert set(event_dict.keys()) == allowed_fields

        # Explicitly assert absence of any parameter/argument payload keys
        assert "parameters" not in event_dict
        assert "arguments" not in event_dict
        assert "payload" not in event_dict
        assert "secret" not in event_dict
        assert "source" not in event_dict

    def test_rejected_approval_runs_zero_tools_and_writes_audit_event(self):
        """Assert that a rejected approval runs ZERO tools and writes the audit event."""
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        sensitive_step = _step(
            "step-dangerous-move",
            tool_name="file.move",
            safety_level=SafetyLevel.D,
            parameters={"source": "/etc/shadow", "destination": "/public/dump"},
        )
        plan = sm.build_plan("sess-audit-rej", "Move sensitive file", [sensitive_step])
        assert sm.state == AgentState.AWAITING_APPROVAL

        # Create approval manager and register the request
        mgr = ApprovalManager()
        req = mgr.create_request(
            plan_id=plan.plan_id,
            session_id="sess-audit-rej",
            safety_level=SafetyLevel.D,
            step_id=sensitive_step.id,
        )

        # Operator rejects the request
        mgr.reject(req.request_id, reason="Access denied: sensitive path violation")

        # Verify audit trail contains the rejection event
        trail = mgr.get_audit_trail()
        assert len(trail) == 1
        assert trail[0].decision == "REJECTED"
        assert trail[0].step_id == sensitive_step.id
        assert trail[0].reason == "Access denied: sensitive path violation"

        # Set up mock executor to verify zero tool invocations
        mock_executor = MockToolExecutor()

        # Manually attempt execution (simulating unauthorized bypass attempt)
        sm.transition_to(AgentState.EXECUTING)
        with pytest.raises(PermissionError) as exc_info:
            sm.execute_plan(executor=mock_executor, approval_manager=mgr)

        assert "not permitted" in str(exc_info.value).lower()
        assert sm.state == AgentState.ERROR

        # STRICT ASSERTION: ZERO tools were executed
        assert len(mock_executor.execution_history) == 0, (
            f"Expected 0 tool executions, but {len(mock_executor.execution_history)} were executed!"
        )
        # Step remains pending or rejected; output is None
        assert sensitive_step.status == "pending"
        assert sensitive_step.result is None
        assert sensitive_step.started_at is None

        # Audit event is intact in the manager audit trail
        assert len(mgr.get_audit_trail()) == 1
        assert mgr.get_audit_trail()[0].decision == "REJECTED"

    def test_expired_approval_runs_zero_tools_and_writes_audit_event(self):
        """Assert that an expired approval runs ZERO tools and writes the audit event."""
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        sensitive_step = _step(
            "step-expired-action",
            tool_name="file.move",
            safety_level=SafetyLevel.C,
            parameters={"source": "/data/a.txt", "destination": "/data/b.txt"},
        )
        plan = sm.build_plan("sess-audit-exp", "Move file with short TTL", [sensitive_step])
        assert sm.state == AgentState.AWAITING_APPROVAL

        # Approval manager with short TTL (0.01s)
        mgr = ApprovalManager(default_ttl_seconds=0.01)
        req = mgr.create_request(
            plan_id=plan.plan_id,
            session_id="sess-audit-exp",
            safety_level=SafetyLevel.C,
            ttl_seconds=0.01,
            step_id=sensitive_step.id,
        )

        # Allow TTL to elapse
        time.sleep(0.02)

        # Set up mock executor to track any tool invocations
        mock_executor = MockToolExecutor()

        # State machine attempts to execute
        sm.transition_to(AgentState.EXECUTING)
        with pytest.raises(PermissionError) as exc_info:
            sm.execute_plan(executor=mock_executor, approval_manager=mgr)

        assert "not permitted" in str(exc_info.value).lower()
        assert sm.state == AgentState.ERROR

        # STRICT ASSERTION: ZERO tools were executed
        assert len(mock_executor.execution_history) == 0, (
            f"Expected 0 tool executions, but {len(mock_executor.execution_history)} were executed!"
        )
        assert sensitive_step.status == "pending"
        assert sensitive_step.result is None
        assert sensitive_step.started_at is None

        # Verify EXPIRED audit event was safely recorded with no sensitive args
        trail = mgr.get_audit_trail()
        assert len(trail) >= 1
        expired_event = [e for e in trail if e.decision == "EXPIRED"][0]
        assert expired_event.step_id == sensitive_step.id
        assert expired_event.decision == "EXPIRED"
        assert "expired" in expired_event.reason.lower()

    def test_state_machine_reject_plan_records_audit_event(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s1 = _step("step-reject-me", tool_name="file.move", safety_level=SafetyLevel.C)
        sm.build_plan("sess-rej-plan", "Reject me", [s1])
        assert sm.state == AgentState.AWAITING_APPROVAL

        rejected_plan = sm.reject_plan("Policy violation")
        assert rejected_plan.status == PlanStatus.REJECTED
        assert len(rejected_plan.audit_trail) == 1
        ev = rejected_plan.audit_trail[0]
        assert ev.decision == "REJECTED"
        assert ev.reason == "Policy violation"

    def test_state_machine_approve_plan_records_audit_event(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s1 = _step("step-approve-me", tool_name="file.move", safety_level=SafetyLevel.C)
        sm.build_plan("sess-app-plan", "Approve me", [s1])
        assert sm.state == AgentState.AWAITING_APPROVAL

        approved_plan = sm.approve_plan()
        assert approved_plan.status == PlanStatus.APPROVED
        assert len(approved_plan.audit_trail) == 1
        ev = approved_plan.audit_trail[0]
        assert ev.decision == "APPROVED"

    def test_no_duplicate_audit_events_on_multiple_checks(self):
        mgr = ApprovalManager(default_ttl_seconds=0.01)
        req = mgr.create_request("p", "s", SafetyLevel.C, ttl_seconds=0.01, step_id="st-1")
        time.sleep(0.02)

        # Multiple expiry checks
        mgr.check_expiry(req.request_id)
        mgr.check_expiry(req.request_id)
        mgr.get_request(req.request_id)

        # Must record exactly 1 expiry event
        assert len(mgr.get_audit_trail()) == 1


# ===========================================================================
# 5. Resilient Executor Tests (Timeouts, Retries, Cancellation)
# ===========================================================================


class TestResilientExecutor:
    def test_cancellation_halts_execution(self):
        ex = MockToolExecutor()
        ex.cancel("User pressed stop")
        assert ex.is_cancelled is True

        res = ex.execute("calc.evaluate", {"expression": "2 + 2"})
        assert res.success is False
        assert "cancelled" in res.error.lower()

        # Reset allows executions again
        ex.reset_cancellation()
        assert ex.is_cancelled is False
        res2 = ex.execute("calc.evaluate", {"expression": "2 + 2"})
        assert res2.success is True

    def test_idempotent_tool_retries_and_succeeds(self):
        ex = MockToolExecutor()
        # Program tool to fail first 2 attempts, succeed on 3rd
        ex.set_fail_first_n_attempts("calc.evaluate", 2)

        res = ex.execute(
            "calc.evaluate",
            {"expression": "5 * 5"},
            is_idempotent=True,
            max_retries=3,
            backoff_base_seconds=0.001,
        )
        assert res.success is True
        assert res.output["result"] == 25.0

    def test_non_idempotent_tool_suppresses_retries(self):
        ex = MockToolExecutor()
        # file.move is non-idempotent
        ex.set_fail_first_n_attempts("file.move", 2)

        res = ex.execute(
            "file.move",
            {"source": "/a", "destination": "/b"},
            is_idempotent=False,
            max_retries=3,
        )
        # Halts immediately on attempt 1 without retrying
        assert res.success is False
        assert "transient" in res.error.lower()

    def test_timeout_enforcement(self):
        ex = MockToolExecutor()
        res = ex.execute(
            "calc.evaluate",
            {"expression": "1 + 1", "simulated_delay": 0.05},
            timeout_seconds=0.01,
        )
        assert res.success is False
        assert "timed out" in res.error.lower()

    def test_execute_step_updates_step_metadata(self):
        ex = MockToolExecutor()
        step = _step("step-calc", tool_name="calc.evaluate", parameters={"expression": "10 / 2"})
        res = ex.execute_step(step)

        assert res.success is True
        assert step.status == "completed"
        assert step.result["result"] == 5.0
        assert step.started_at is not None
        assert step.completed_at is not None
        assert len(step.execution_logs) > 0


# ===========================================================================
# 6. State Machine Integration & Topological Execution
# ===========================================================================


class TestStateMachineIntegration:
    def test_execute_plan_in_topological_order(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s1 = _step("s1", tool_name="file.search", parameters={"pattern": "*.py"}, step_number=1)
        s2 = _step("s2", tool_name="calc.evaluate", parameters={"expression": "10 + 5"}, depends_on=["s1"], step_number=2)

        plan = sm.build_plan("session-dag", "DAG execution", [s2, s1])
        # Auto-approved (SafetyLevel A) -> EXECUTING
        assert sm.state == AgentState.EXECUTING

        executed_plan = sm.execute_plan()
        assert executed_plan.status == PlanStatus.COMPLETED
        assert sm.state == AgentState.IDLE
        assert s1.status == "completed"
        assert s2.status == "completed"

    def test_execute_plan_respects_approval_gate(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s_sensitive = _step(
            "s-move",
            tool_name="file.move",
            safety_level=SafetyLevel.C,
            parameters={"source": "/src", "destination": "/dst"},
        )
        plan = sm.build_plan("session-appr", "Move file", [s_sensitive])
        assert sm.state == AgentState.AWAITING_APPROVAL

        # Cannot execute before approval while in AWAITING_APPROVAL
        with pytest.raises(InvalidTransitionError):
            sm.execute_plan()

        # Approve and execute
        sm.approve_plan()
        assert sm.state == AgentState.EXECUTING
        sm.execute_plan(granted_scopes=[PermissionScope.WORKSPACE_WRITE])
        assert sm.state == AgentState.IDLE
        assert plan.status == PlanStatus.COMPLETED

    def test_execute_plan_unapproved_in_executing_state_raises_permission_error(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)
        s_sensitive = _step(
            "s-move",
            tool_name="file.move",
            safety_level=SafetyLevel.C,
            parameters={"source": "/src", "destination": "/dst"},
        )
        plan = sm.build_plan("sess-unappr", "Move", [s_sensitive])
        # Manually jump to EXECUTING without approving
        sm.transition_to(AgentState.EXECUTING)
        assert plan.approved_at is None

        with pytest.raises(PermissionError):
            sm.execute_plan()
        assert sm.state == AgentState.ERROR

    def test_execute_plan_blocked_by_approval_manager_if_expired(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s_sensitive = _step(
            "s-del",
            tool_name="file.move",
            safety_level=SafetyLevel.D,
            parameters={"source": "/old", "destination": "/trash"},
        )
        plan = sm.build_plan("session-exp", "Delete", [s_sensitive])

        mgr = ApprovalManager(default_ttl_seconds=0.01)
        mgr.create_request(plan.plan_id, "session-exp", SafetyLevel.D, ttl_seconds=0.01)
        time.sleep(0.02)

        sm.approve_plan()
        assert sm.state == AgentState.EXECUTING

        # Manager determines it expired
        with pytest.raises(PermissionError):
            sm.execute_plan(approval_manager=mgr)

        assert sm.state == AgentState.ERROR

    def test_execute_plan_cancellation(self):
        sm = AgentStateMachine()
        sm.transition_to(AgentState.LISTENING)
        sm.transition_to(AgentState.PLANNING)

        s1 = _step("s1", tool_name="file.search")
        plan = sm.build_plan("sess-canc", "Cancel test", [s1])

        ex = MockToolExecutor()
        ex.cancel("Manual cancel")

        sm.execute_plan(executor=ex)
        assert plan.status == PlanStatus.CANCELLED
        assert sm.state == AgentState.ERROR
