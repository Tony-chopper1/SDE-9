"""
Context and Reasoning Module
Owner: Praveen Kumar R (feature/context-reasoning)
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import time


class WindowContext(BaseModel):
    app_name: str = "VS Code"
    window_title: str = "app.py - project"
    app_type: str = "ide"
    visible_snippet: Optional[str] = None


class ConversationTurn(BaseModel):
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: float = Field(default_factory=time.time)


class ConversationContext(BaseModel):
    session_id: str
    active_window: WindowContext = Field(default_factory=WindowContext)
    history: List[ConversationTurn] = Field(default_factory=list)
    user_query: str = ""
    timestamp: float = Field(default_factory=time.time)


class ReasoningResult(BaseModel):
    intent: str
    requires_tool: bool
    planned_tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, str]] = None
    direct_response: Optional[str] = None
    confidence: float = 0.95
