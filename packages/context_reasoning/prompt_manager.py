"""
Versioned Prompt Manager for AI Voice Co-Pilot.

Manages version-controlled prompt templates with placeholder variable substitution,
validation, and fallback handling.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from packages.context_reasoning.models import VersionedPromptTemplate


DEFAULT_V1_0_TEMPLATE = """You are an intelligent AI Voice Co-Pilot assisting a software engineer.

[CURRENT ENVIRONMENT]
Active Application: {app_name}
Visible Code / Screen Snippet:
```
{snippet}
```

[CONVERSATION HISTORY]
{history}

[USER REQUEST]
{query}

Analyze the user's request in the context of the active screen snippet and conversation history. Respond concisely and accurately."""

DEFAULT_V1_1_TEMPLATE = """You are an intelligent AI Voice Co-Pilot assisting a developer.

[CONTEXT]
Application: {app_name}
Snippet:
{snippet}

[HISTORY]
{history}

[USER QUERY]
{query}

Classify the user intent and decide whether tool execution is required.
Available Tools:
- file.search: search directory for files matching a pattern
- file.move: relocate or rename a file
- calc.evaluate: evaluate a mathematical expression

Output format:
Intent: <INTENT>
Requires Tool: <true/false>
Tool: <tool_name or none>
Response: <direct response to the user>"""

DEFAULT_V2_0_TEMPLATE = """You are an autonomous AI Voice Co-Pilot operating with Safety Level validation.

[SYSTEM METRICS]
Active App: {app_name}
Window Title: {window_title}
Visible Content:
{snippet}

[RECENT DIALOGUE]
{history}

[INCOMING INSTRUCTION]
{query}

[SAFETY GUIDELINES]
- Level A (Informational): Safe queries, code explanations, status checks.
- Level B (Low Risk): Read-only operations, file searches, non-destructive calculations.
- Level C (Sensitive): File modifications, relocations, git commits (requires user approval).
- Level D (Destructive): File deletions, branch overwrites, terminal system changes.

Generate an executable reasoning plan adhering strictly to safety guidelines."""


class VersionedPromptManager:
    """
    Manages version-controlled prompt templates with placeholder replacement.

    Features:
    - Built-in versioned templates ('v1.0', 'v1.1', 'v2.0').
    - Dynamic placeholder extraction and validation.
    - Safe variable rendering with customizable fallbacks.
    - Template registration and version inspection.
    """

    def __init__(self, default_version: str = "v1.0") -> None:
        """Initialize prompt manager and register built-in template versions."""
        self._prompts: Dict[str, VersionedPromptTemplate] = {}
        self.default_version: str = default_version

        # Register baseline built-in templates
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register the built-in default templates."""
        self.register_template(
            version="v1.0",
            template=DEFAULT_V1_0_TEMPLATE,
            description="Baseline contextual prompt with active app, snippet, history, and query.",
        )
        self.register_template(
            version="v1.1",
            template=DEFAULT_V1_1_TEMPLATE,
            description="Tool-oriented reasoning prompt specifying supported tools and decision format.",
        )
        self.register_template(
            version="v2.0",
            template=DEFAULT_V2_0_TEMPLATE,
            description="Enterprise safety-gated agentic prompt with Safety Levels A-D guidelines.",
        )

    def register_template(
        self,
        version: str,
        template: str,
        description: str = "",
        variables: Optional[List[str]] = None,
    ) -> VersionedPromptTemplate:
        """
        Register a new version-controlled prompt template.

        Args:
            version: Unique version tag (e.g., 'v1.0', 'v2.1-custom').
            template: The raw prompt string containing `{variable}` placeholders.
            description: Optional human-readable description of this version's purpose.
            variables: Optional explicit list of required variables. If None, auto-detected.

        Returns:
            Registered VersionedPromptTemplate instance.
        """
        if not version or not version.strip():
            raise ValueError("Template version cannot be empty.")
        if not template or not template.strip():
            raise ValueError("Template content cannot be empty.")

        # Auto-detect variables inside {variable_name} placeholders
        detected_vars = re.findall(r"\{([a-zA-Z0-9_]+)\}", template)
        unique_vars = sorted(list(set(variables or detected_vars)))

        prompt_obj = VersionedPromptTemplate(
            version=version.strip(),
            template=template,
            variables=unique_vars,
            description=description,
            created_at=time.time(),
        )
        self._prompts[version.strip()] = prompt_obj
        return prompt_obj

    def get_template(self, version: Optional[str] = None) -> VersionedPromptTemplate:
        """
        Retrieve a registered template by version string.

        Args:
            version: Version tag to retrieve. Defaults to default_version.

        Returns:
            VersionedPromptTemplate instance.

        Raises:
            KeyError: If the specified version is not registered.
        """
        target_version = (version or self.default_version).strip()
        if target_version not in self._prompts:
            available = ", ".join(sorted(self._prompts.keys()))
            raise KeyError(
                f"Prompt template version '{target_version}' not found. Available versions: [{available}]"
            )
        return self._prompts[target_version]

    def render_prompt(
        self,
        version: Optional[str] = None,
        app_name: str = "VS Code",
        snippet: str = "(No visible code snippet)",
        query: str = "",
        history: str = "(No prior conversation)",
        window_title: str = "workspace",
        **kwargs: Any,
    ) -> str:
        """
        Render a versioned prompt template with variable substitution.

        Args:
            version: Version tag to render. Defaults to default_version.
            app_name: Active application name.
            snippet: Code or screen text snippet.
            query: User's voice/text query.
            history: Formatted conversation history.
            window_title: Window title text.
            **kwargs: Additional template variables.

        Returns:
            Fully rendered prompt string.
        """
        template_obj = self.get_template(version)

        # Merge standard arguments with custom kwargs
        params: Dict[str, Any] = {
            "app_name": app_name or "VS Code",
            "snippet": snippet if snippet is not None else "(No visible code snippet)",
            "query": query or "",
            "history": history or "(No prior conversation)",
            "window_title": window_title or "workspace",
        }
        params.update(kwargs)

        # Provide a fallback string for any placeholder present in template but absent in params
        class DefaultPlaceholderDict(dict):
            def __missing__(self, key: str) -> str:
                return f"[{key}: not provided]"

        safe_params = DefaultPlaceholderDict(params)
        return template_obj.template.format_map(safe_params)

    def list_versions(self) -> List[str]:
        """Return a sorted list of all registered version strings."""
        return sorted(list(self._prompts.keys()))

    def set_default_version(self, version: str) -> None:
        """Change the default template version."""
        if version not in self._prompts:
            raise KeyError(f"Cannot set unknown version '{version}' as default.")
        self.default_version = version
