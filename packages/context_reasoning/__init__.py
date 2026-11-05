"""
Context and Reasoning Package.

Exposes context management, versioned prompt templates, mock reasoning services,
and domain models for AI Voice Co-Pilot.
"""
from packages.context_reasoning.models import (
    WindowContext,
    ConversationTurn,
    ConversationContext,
    VersionedPromptTemplate,
    ReasoningResult,
)
from packages.context_reasoning.context_manager import ContextManager
from packages.context_reasoning.prompt_manager import VersionedPromptManager
from packages.context_reasoning.mock_reasoning import MockReasoningService

__all__ = [
    "WindowContext",
    "ConversationTurn",
    "ConversationContext",
    "VersionedPromptTemplate",
    "ReasoningResult",
    "ContextManager",
    "VersionedPromptManager",
    "MockReasoningService",
]
