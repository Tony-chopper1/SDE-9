"""
Context and Reasoning Package.

Exposes multimodal context management, opt-in screen capture, OCR/vision adapters,
bounded context building, versioned prompt templates, mock reasoning services,
and resilient LLM adapters for the AI Voice Co-Pilot.
"""
from packages.context_reasoning.models import (
    WindowContext,
    SourceReference,
    ContextItem,
    Observation,
    ScreenContext,
    ConversationTurn,
    ConversationContext,
    VersionedPromptTemplate,
    ReasoningRequest,
    ReasoningResult,
    VisionRegion,
    VisionResult,
    LLMResponse,
    CaptureConfig,
    ContextBuilderConfig,
)
from packages.context_reasoning.exceptions import (
    ContextReasoningError,
    CaptureDisabledError,
    SamplingRateLimitError,
    FrameSizeLimitError,
    VisionProcessingError,
    LLMError,
    LLMTimeoutError,
    LLMRetryExhaustedError,
    MalformedOutputError,
)
from packages.context_reasoning.context_manager import ContextManager
from packages.context_reasoning.prompt_manager import (
    VersionedPromptManager,
    format_untrusted_block,
    sanitize_untrusted_text,
)
from packages.context_reasoning.mock_reasoning import MockReasoningService
from packages.context_reasoning.capture_adapter import CaptureAdapter
from packages.context_reasoning.vision_adapter import BaseVisionAdapter, MockVisionAdapter
from packages.context_reasoning.context_builder import ContextBuilder, approximate_tokens
from packages.context_reasoning.llm_adapter import BaseLLMClient, MockLLMClient, LLMAdapter

__all__ = [
    # Domain Models
    "WindowContext",
    "SourceReference",
    "ContextItem",
    "Observation",
    "ScreenContext",
    "ConversationTurn",
    "ConversationContext",
    "VersionedPromptTemplate",
    "ReasoningRequest",
    "ReasoningResult",
    "VisionRegion",
    "VisionResult",
    "LLMResponse",
    "CaptureConfig",
    "ContextBuilderConfig",
    "Observation",

    "ContextReasoningError",
    "CaptureDisabledError",
    "SamplingRateLimitError",
    "FrameSizeLimitError",
    "VisionProcessingError",
    "LLMError",
    "LLMTimeoutError",
    "LLMRetryExhaustedError",
    "MalformedOutputError",
    # Core Components
    "ContextManager",
    "VersionedPromptManager",
    "MockReasoningService",
    "CaptureAdapter",
    "BaseVisionAdapter",
    "MockVisionAdapter",
    "ContextBuilder",
    "approximate_tokens",
    "BaseLLMClient",
    "MockLLMClient",
    "LLMAdapter",
    "format_untrusted_block",
    "sanitize_untrusted_text",
]
