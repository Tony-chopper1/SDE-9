"""
Allow-listed tool registry and permission scope enforcement.

Maintains registered tool specifications, enforces parameter schemas,
and validates caller permission scopes before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Collection, Dict, Optional, Set

from packages.agentic_workflow.models import PermissionScope, SafetyLevel
from packages.agentic_workflow.validator import PlanValidationError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolNotFoundError(PlanValidationError):
    """Raised when an unregistered or disallowed tool is invoked."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' is not registered in the allow-list.")


class ToolParameterError(PlanValidationError):
    """Raised when tool arguments fail parameter schema validation."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Invalid parameters for tool '{tool_name}': {message}")


class PermissionDeniedError(Exception):
    """Raised when the caller lacks the required permission scope to invoke a tool."""

    def __init__(
        self,
        tool_name: str,
        required_scope: PermissionScope,
        granted_scopes: Collection[PermissionScope],
    ) -> None:
        self.tool_name = tool_name
        self.required_scope = required_scope
        self.granted_scopes = set(granted_scopes)
        granted_str = ", ".join(s.value for s in self.granted_scopes) or "none"
        super().__init__(
            f"Permission denied for tool '{tool_name}'. "
            f"Required scope: '{required_scope.value}', granted: [{granted_str}]"
        )


# ---------------------------------------------------------------------------
# Tool Specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    """Specification defining permissions, idempotency, and parameter schema for a tool.

    Attributes:
        name: Dot-namespaced tool identifier.
        permission_scope: Minimal permission boundary required.
        is_idempotent: Whether repeated invocations produce identical side-effects.
        safety_level: Default risk classification.
        required_parameters: Dict of parameter name to expected Python type.
        optional_parameters: Dict of parameter name to expected Python type.
        description: Human-readable description of tool capabilities.
    """

    name: str
    permission_scope: PermissionScope
    is_idempotent: bool
    safety_level: SafetyLevel
    required_parameters: Dict[str, type] = field(default_factory=dict)
    optional_parameters: Dict[str, type] = field(default_factory=dict)
    description: str = ""


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry of authorized tools with schema and scope enforcement."""

    def __init__(self, load_defaults: bool = True) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        if load_defaults:
            self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default allow-listed tools: file.search, file.move, calc.evaluate."""
        self.register(
            ToolSpec(
                name="file.search",
                permission_scope=PermissionScope.READ_ONLY,
                is_idempotent=True,
                safety_level=SafetyLevel.A,
                required_parameters={},
                optional_parameters={
                    "pattern": str,
                    "directory": str,
                    "max_results": int,
                },
                description="Simulates directory scanning and file searching.",
            )
        )
        self.register(
            ToolSpec(
                name="file.move",
                permission_scope=PermissionScope.WORKSPACE_WRITE,
                is_idempotent=False,
                safety_level=SafetyLevel.C,
                required_parameters={
                    "source": str,
                    "destination": str,
                },
                optional_parameters={
                    "overwrite": bool,
                },
                description="Simulates moving or renaming files within workspace.",
            )
        )
        self.register(
            ToolSpec(
                name="calc.evaluate",
                permission_scope=PermissionScope.READ_ONLY,
                is_idempotent=True,
                safety_level=SafetyLevel.A,
                required_parameters={
                    "expression": str,
                },
                optional_parameters={},
                description="Safely evaluates basic arithmetic expressions.",
            )
        )

    def register(self, spec: ToolSpec) -> None:
        """Register an authorized tool specification."""
        self._tools[spec.name] = spec

    def unregister(self, tool_name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(tool_name, None)

    def is_registered(self, tool_name: str) -> bool:
        """Check if a tool is registered in the allow-list."""
        return tool_name in self._tools

    def get_spec(self, tool_name: str) -> ToolSpec:
        """Retrieve the specification for a registered tool.

        Raises:
            ToolNotFoundError: If the tool is not registered.
        """
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name)
        return self._tools[tool_name]

    def list_tools(self) -> List[str]:
        """Return the names of all currently registered tools."""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # Permission Scope Validation
    # ------------------------------------------------------------------

    @staticmethod
    def is_scope_sufficient(
        required: PermissionScope, granted: Collection[PermissionScope]
    ) -> bool:
        """Check whether the granted scopes satisfy the required scope."""
        granted_set = set(granted)
        if PermissionScope.SYSTEM_EXEC in granted_set:
            return True
        if required in granted_set:
            return True
        if (
            required == PermissionScope.READ_ONLY
            and PermissionScope.WORKSPACE_WRITE in granted_set
        ):
            return True
        return False

    def check_permission(
        self, tool_name: str, granted_scopes: Collection[PermissionScope]
    ) -> bool:
        """Check whether *granted_scopes* permit invoking *tool_name*.

        Raises:
            ToolNotFoundError: If *tool_name* is not registered.
        """
        spec = self.get_spec(tool_name)
        return self.is_scope_sufficient(spec.permission_scope, granted_scopes)

    def enforce_permission(
        self, tool_name: str, granted_scopes: Collection[PermissionScope]
    ) -> None:
        """Enforce that *granted_scopes* satisfy *tool_name* requirements.

        Raises:
            ToolNotFoundError: If *tool_name* is not registered.
            PermissionDeniedError: If *granted_scopes* are insufficient.
        """
        spec = self.get_spec(tool_name)
        if not self.is_scope_sufficient(spec.permission_scope, granted_scopes):
            raise PermissionDeniedError(
                tool_name=tool_name,
                required_scope=spec.permission_scope,
                granted_scopes=granted_scopes,
            )

    # ------------------------------------------------------------------
    # Parameter Schema Validation
    # ------------------------------------------------------------------

    def validate_parameters(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> None:
        """Validate input parameters against the tool's defined schema.

        Raises:
            ToolNotFoundError: If *tool_name* is not registered.
            ToolParameterError: If required parameters are missing or of incorrect type.
        """
        spec = self.get_spec(tool_name)

        # 1. Check required parameters
        for param_name, expected_type in spec.required_parameters.items():
            if param_name not in parameters:
                raise ToolParameterError(
                    tool_name=tool_name,
                    message=f"Missing required parameter '{param_name}'",
                )
            val = parameters[param_name]
            if not isinstance(val, expected_type):
                raise ToolParameterError(
                    tool_name=tool_name,
                    message=(
                        f"Parameter '{param_name}' expected type {expected_type.__name__}, "
                        f"got {type(val).__name__}"
                    ),
                )
            # Empty string check for strings
            if expected_type is str and not str(val).strip():
                raise ToolParameterError(
                    tool_name=tool_name,
                    message=f"Parameter '{param_name}' must not be an empty string",
                )

        # 2. Check types of optional parameters if supplied
        for param_name, val in parameters.items():
            if param_name in spec.optional_parameters:
                expected_type = spec.optional_parameters[param_name]
                if not isinstance(val, expected_type):
                    # Special case: int for float or bool for int if strictly bool
                    if expected_type is int and isinstance(val, bool):
                        raise ToolParameterError(
                            tool_name=tool_name,
                            message=(
                                f"Parameter '{param_name}' expected int, got bool"
                            ),
                        )
                    if not isinstance(val, expected_type):
                        raise ToolParameterError(
                            tool_name=tool_name,
                            message=(
                                f"Parameter '{param_name}' expected type {expected_type.__name__}, "
                                f"got {type(val).__name__}"
                            ),
                        )
