"""
Context and Reasoning Domain Models.

Provides Pydantic schemas for active window tracking, conversation turns,
multimodal context snapshots, versioned prompt templates, and structured
reasoning results.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class WindowContext(BaseModel):
    """Represents context from the active operating system application/window."""
    model_config = ConfigDict(extra="ignore")

    app_name: str = "VS Code"
    window_title: str = "app.py - project"
    app_type: Literal["ide", "browser", "terminal", "document", "other"] = "ide"
    visible_snippet: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    """Represents a single message turn in the conversation history."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: Literal["user", "assistant", "system"] = "user"
    content: str
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationContext(BaseModel):
    """Complete conversational context state for a session at a given instant."""
    model_config = ConfigDict(extra="ignore")

    session_id: str
    active_window: WindowContext = Field(default_factory=WindowContext)
    history: List[ConversationTurn] = Field(default_factory=list)
    user_query: str = ""
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VersionedPromptTemplate(BaseModel):
    """Represents an immutable, version-controlled prompt template."""
    model_config = ConfigDict(extra="ignore")

    version: str
    template: str
    variables: List[str] = Field(default_factory=list)
    description: str = ""
    created_at: float = Field(default_factory=time.time)


class ReasoningResult(BaseModel):
    """Structured decision output produced by the reasoning engine."""
    model_config = ConfigDict(extra="ignore")

    intent: str
    requires_tool: bool
    planned_tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    direct_response: Optional[str] = None
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    reasoning_steps: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
