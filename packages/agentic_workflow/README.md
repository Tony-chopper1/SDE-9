# Agentic Workflow Module (`packages/agentic_workflow/`)

> **Owner**: Chirantan R Kuppelur · Branch: `feature/agentic-workflow`  
> **Module**: W4 – Agentic Workflow: Schemas, State Machine, Harmless Tools & Safety Gate

---

## Overview

The `agentic_workflow` package provides the core orchestration layer for the SDK-9 AI Voice Co-Pilot. It implements:
- **Standardized Domain Schemas**: `WorkflowPlan`, `WorkflowStep`, `ToolSpec`, `ApprovalRequest`, and `WorkflowResult` (with backward-compatible aliases `ActionPlan` and `ToolResult`).
- **Finite-State Machine (`AgentStateMachine`)**: Governs multi-step agent decisions, transitions, and lifecycle state tracking with millisecond timestamps.
- **Safety Gate**: Categorizes operations into Safety Levels A–D, enforcing human approval for sensitive (`SafetyLevel.C`) and destructive (`SafetyLevel.D`) actions before execution.
- **Strictly Harmless Mock Tool Executor**: Exactly two harmless mock tools (`file.search` and `calc.evaluate`). Consequential tools like `file.move` or external sending have been removed to prevent side-effects.
- **DAG Dependency Analysis**: Validates step dependencies and detects circular cycles using 3-color DFS.
- **Approval Gate & Safe Audit Trail**: Configurable TTL expiration and safe audit logging without sensitive parameters.

---

## Module Layout

```
packages/agentic_workflow/
├── __init__.py          # Public API re-exports
├── models.py            # WorkflowPlan, WorkflowStep, ToolSpec, ApprovalRequest, WorkflowResult
├── state_machine.py     # AgentStateMachine FSM with safety gate & topological execution
├── mock_executor.py     # MockToolExecutor (harmless mock tools: file.search, calc.evaluate)
├── validator.py         # DAG cycle detection & topological ordering
├── registry.py          # Allow-listed tool registry & permission scopes
├── approval.py          # Approval request lifecycle, TTL expiry & safe audit trail
├── types.ts             # TypeScript interfaces mirroring all schemas
└── tests/
    ├── test_agentic_workflow.py        # Week 1 tests (129 tests)
    └── test_validation_and_safety.py   # Week 2 tests
```

---

## Standard Schemas

| Schema | Purpose | Key Attributes |
|---|---|---|
| **`WorkflowPlan`** | Multi-step agentic execution plan | `plan_id`, `session_id`, `goal`, `steps`, `overall_safety_level`, `requires_approval`, `approved_at`, `rejected_at`, `rejection_reason`, `audit_trail` |
| **`WorkflowStep`** | Discrete action step in a plan | `id`, `step_number`, `description`, `tool_name`, `parameters`, `safety_level`, `status`, `retry_count`, `depends_on`, `timeout_seconds`, `is_idempotent`, `execution_logs` |
| **`ToolSpec`** | Specification of an authorized tool | `name`, `description`, `safety_level`, `is_idempotent`, `parameters`, `required_parameters`, `permission_scope` |
| **`ApprovalRequest`** | Human-in-the-loop approval contract | `request_id`, `plan_id`, `session_id`, `safety_level`, `status`, `expires_at`, `decided_at`, `decided_by`, `reason`, `step_id` |
| **`WorkflowResult`** | Standard result of tool execution | `tool_name`, `success`, `output`, `duration_ms`, `error`, `timestamp` |

> *Note: For backwards compatibility, aliases `ActionPlan = WorkflowPlan` and `ToolResult = WorkflowResult` are provided.*

---

## Safety Classification Levels

| Level | Name | Approval Required | Description |
|:---:|:---|:---:|:---|
| **A** | Informational | No | Read-only inspection; zero side-effects (e.g. `file.search`, `calc.evaluate`). Auto-proceeds to `EXECUTING`. |
| **B** | Low Risk | No | Minor writes or notifications. Auto-proceeds with audit log. |
| **C** | Sensitive | **Yes** | Modifies significant state. Requires explicit human sign-off (`AWAITING_APPROVAL`). |
| **D** | Destructive | **Yes** | High-impact actions. Requires explicit human sign-off (`AWAITING_APPROVAL`). |

---

## Harmless Mock Tools

Per safety requirements, consequential operations (such as file moving/renaming, disk modifications, or external communications) have been removed. Exactly two harmless in-memory mock tools are registered:

1. **`file.search`** (`SafetyLevel.A`, Informational):
   - Harmless, read-only simulation of glob directory scanning.
   - Parameters: `pattern` (str, default: `*`), `directory` (str, default: `/`), `max_results` (int, default: `10`).
   - Generates simulated paths deterministically without disk operations.

2. **`calc.evaluate`** (`SafetyLevel.A`, Informational):
   - Purely in-memory evaluation of arithmetic expressions using a restricted Python AST evaluator.
   - Parameters: `expression` (str, required).
   - Supported operators: `+`, `-`, `*`, `/`, `//`, `%`, `**`, unary `+` and `-`.
   - Function calls, variable lookups, and built-ins are strictly disallowed.

---

## State Machine Lifecycle

```
    ┌──────┐       listening       ┌───────────┐       plan        ┌──────────┐
    │ IDLE │ ────────────────────> │ LISTENING │ ────────────────> │ PLANNING │
    └──────┘ <──────────────────── └───────────┘                   └──────────┘
       ^             cancel                                              │
       │                                            needs_approval=True  │  needs_approval=False
       │                                           ┌─────────────────────┴──────────────────┐
       │                                           ▼                                        ▼
       │     reject                       ┌───────────────────┐      approve         ┌───────────┐
       ├───────────────────────────────── │ AWAITING_APPROVAL │ ───────────────────> │ EXECUTING │
       │                                  └───────────────────┘                      └───────────┘
       │                                                                                   │
       │                                                                                   ▼
       │     complete                                                                ┌───────────┐
       ├──────────────────────────────────────────────────────────────────────────── │ VERIFYING │
       │                                                                             └───────────┘
       │                                                                                   │
       │     response sent                                                                 ▼
       │ <────────────────────────────────────────────────────────────────────────── ┌────────────┐
       │                                                                             │ RESPONDING │
       │                                                                             └────────────┘
       │     reset
       └─── ┌───────┐
            │ ERROR │ <── (Any state on failure / approval rejection)
            └───────┘
```

---

## Quickstart Example

```python
from packages.agentic_workflow import (
    AgentStateMachine,
    AgentState,
    WorkflowStep,
    SafetyLevel,
    MockToolExecutor,
)

# 1. Initialize State Machine
sm = AgentStateMachine()
sm.transition_to(AgentState.LISTENING)
sm.transition_to(AgentState.PLANNING)

# 2. Build Plan with Harmless Mock Tool
step = WorkflowStep(
    step_number=1,
    description="Calculate sales tax",
    tool_name="calc.evaluate",
    safety_level=SafetyLevel.A,
    parameters={"expression": "250 * 0.08"},
)

plan = sm.build_plan(session_id="sess-01", goal="Tax calculation", steps=[step])
assert sm.state == AgentState.EXECUTING

# 3. Execute with Mock Tool Executor
executor = MockToolExecutor()
result = executor.execute(step.tool_name, step.parameters)
assert result.success is True
assert result.output["result"] == 20.0

# 4. Complete Lifecycle
sm.transition_to(AgentState.VERIFYING)
sm.transition_to(AgentState.RESPONDING)
sm.transition_to(AgentState.IDLE)
```

---

## Testing & Coverage

Run the tests with pytest:

```bash
# Run unit and integration tests with coverage
.venv/bin/pytest packages/agentic_workflow/tests/ -v

# Full monorepo suite
.venv/bin/pytest
```
