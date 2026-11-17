"""
Plan validation and DAG dependency analysis for the Agentic Workflow module.

Provides cycle detection via DFS coloring, missing dependency detection,
and topological sorting for workflow plans.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Union

from packages.agentic_workflow.models import ActionPlan, WorkflowPlan, WorkflowStep


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PlanValidationError(Exception):
    """Base exception for all workflow plan validation failures."""


class CircularDependencyError(PlanValidationError):
    """Raised when a circular prerequisite dependency is detected in a plan.

    Attributes:
        cycle_path: Ordered list of step IDs representing the cycle loop.
    """

    def __init__(
        self,
        cycle_path: Union[List[str], str],
        message: Optional[str] = None,
    ) -> None:
        if isinstance(cycle_path, list):
            self.cycle_path: List[str] = cycle_path
            path_str = " -> ".join(cycle_path)
        else:
            self.cycle_path = [cycle_path]
            path_str = cycle_path

        msg = message or f"Circular dependency detected: {path_str}"
        super().__init__(msg)


class MissingDependencyError(PlanValidationError):
    """Raised when a step depends on another step ID not present in the plan.

    Attributes:
        step_id: The ID of the step with the unresolvable dependency.
        missing_dep: The missing prerequisite step ID.
    """

    def __init__(self, step_id: str, missing_dep: str) -> None:
        self.step_id = step_id
        self.missing_dep = missing_dep
        super().__init__(
            f"Step '{step_id}' depends on missing prerequisite step '{missing_dep}'"
        )


# ---------------------------------------------------------------------------
# Plan Validator
# ---------------------------------------------------------------------------


class PlanValidator:
    """Validates ActionPlan / WorkflowPlan structure and dependency graphs.

    Features:
        * Detects missing prerequisite step dependencies (:class:`MissingDependencyError`).
        * Detects circular dependencies via DFS 3-color cycle detection (:class:`CircularDependencyError`).
        * Computes deterministic prerequisite execution order (:meth:`get_topological_order`).
    """

    @classmethod
    def _extract_steps(
        cls, plan_or_steps: Union[ActionPlan, WorkflowPlan, List[WorkflowStep]]
    ) -> List[WorkflowStep]:
        """Normalize input into a list of :class:`WorkflowStep` objects."""
        if isinstance(plan_or_steps, (ActionPlan, WorkflowPlan)):
            return plan_or_steps.steps
        return plan_or_steps

    @classmethod
    def validate(
        cls, plan_or_steps: Union[ActionPlan, WorkflowPlan, List[WorkflowStep]]
    ) -> bool:
        """Validate that all step dependencies exist and form an acyclic graph (DAG).

        Args:
            plan_or_steps: An :class:`ActionPlan`, :class:`WorkflowPlan`, or list of steps.

        Returns:
            ``True`` if the plan satisfies all DAG invariants.

        Raises:
            MissingDependencyError: If a step depends on an unknown step ID.
            CircularDependencyError: If any directed cycle exists among dependencies.
            PlanValidationError: If duplicate step IDs exist.
        """
        steps = cls._extract_steps(plan_or_steps)
        if not steps:
            return True

        # Check for unique step IDs
        seen_ids: Set[str] = set()
        for step in steps:
            if step.id in seen_ids:
                raise PlanValidationError(f"Duplicate step ID '{step.id}' found in plan.")
            seen_ids.add(step.id)

        # 1. Missing dependency check
        step_map: Dict[str, WorkflowStep] = {s.id: s for s in steps}
        for step in steps:
            for dep_id in step.depends_on:
                if dep_id not in step_map:
                    raise MissingDependencyError(step_id=step.id, missing_dep=dep_id)

        # 2. Cycle detection via DFS 3-coloring
        # Colors: 0 = WHITE (unvisited), 1 = GRAY (visiting / on stack), 2 = BLACK (visited)
        colors: Dict[str, int] = {s.id: 0 for s in steps}
        recursion_stack: List[str] = []

        def dfs(current_id: str) -> None:
            colors[current_id] = 1  # GRAY
            recursion_stack.append(current_id)

            current_step = step_map[current_id]
            for dep_id in current_step.depends_on:
                if colors[dep_id] == 1:
                    # Found a cycle back to a node in the current recursion stack
                    cycle_start_index = recursion_stack.index(dep_id)
                    cycle_path = recursion_stack[cycle_start_index:] + [dep_id]
                    raise CircularDependencyError(cycle_path=cycle_path)
                elif colors[dep_id] == 0:
                    dfs(dep_id)

            recursion_stack.pop()
            colors[current_id] = 2  # BLACK

        for step in steps:
            if colors[step.id] == 0:
                dfs(step.id)

        return True

    @classmethod
    def get_topological_order(
        cls, plan_or_steps: Union[ActionPlan, WorkflowPlan, List[WorkflowStep]]
    ) -> List[str]:
        """Compute the prerequisite execution order of step IDs.

        Ensures that if step B depends on step A, then A appears before B
        in the returned list.

        Args:
            plan_or_steps: An :class:`ActionPlan`, :class:`WorkflowPlan`, or list of steps.

        Returns:
            Ordered list of step IDs from earliest prerequisite to final dependent.

        Raises:
            MissingDependencyError: If a prerequisite step ID is missing.
            CircularDependencyError: If a circular dependency prevents topological ordering.
        """
        # Validate first to catch missing deps and cycles with full cycle path
        cls.validate(plan_or_steps)

        steps = cls._extract_steps(plan_or_steps)
        if not steps:
            return []

        step_map: Dict[str, WorkflowStep] = {s.id: s for s in steps}

        # in_degree: number of prerequisites that must be completed before step s
        in_degree: Dict[str, int] = {s.id: len(s.depends_on) for s in steps}

        # dependents: map from prerequisite p -> list of steps that depend on p
        dependents: Dict[str, List[str]] = {s.id: [] for s in steps}
        for s in steps:
            for dep_id in s.depends_on:
                dependents[dep_id].append(s.id)

        # Initial queue: steps with in_degree == 0 (no prerequisites)
        # Order by step_number for deterministic order among independent steps
        ready: List[str] = [
            s.id for s in sorted(steps, key=lambda x: (x.step_number, x.id))
            if in_degree[s.id] == 0
        ]

        ordered_step_ids: List[str] = []

        while ready:
            current_id = ready.pop(0)
            ordered_step_ids.append(current_id)

            for dep_step_id in dependents.get(current_id, []):
                in_degree[dep_step_id] -= 1
                if in_degree[dep_step_id] == 0:
                    ready.append(dep_step_id)
                    # Re-sort ready queue by step_number for deterministic tie-breaking
                    ready.sort(key=lambda sid: (step_map[sid].step_number, sid))

        if len(ordered_step_ids) != len(steps):
            raise CircularDependencyError(
                cycle_path=ordered_step_ids,
                message="Graph contains a circular dependency preventing topological sort.",
            )

        return ordered_step_ids
