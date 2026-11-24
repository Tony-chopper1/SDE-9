"""
Context and Reasoning Domain Models.

Provides Pydantic schemas for active window tracking, conversation turns,
multimodal context snapshots, versioned prompt templates, structured
reasoning requests and results, context items, source references, and screen frames.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WindowContext(BaseModel):
    """Represents context from the active operating system application/window."""
    model_config = ConfigDict(extra="ignore")

    app_name: str = Field(
        default="VS Code",
        description="Name of the active foreground application (e.g., 'VS Code', 'Chrome').",
    )
    window_title: str = Field(
        default="app.py - project",
        description="Text displayed in the title bar of the active window.",
    )
    app_type: Literal["ide", "browser", "terminal", "document", "other"] = Field(
        default="ide",
        description="Classification category of the application (ide, browser, terminal, document, other).",
    )
    visible_snippet: Optional[str] = Field(
        default=None,
        description="Text or source code snippet currently visible in the active editor/window.",
    )
    url: Optional[str] = Field(
        default=None,
        description="Current browser URL if the active application is a web browser.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional key-value metadata associated with the window.",
    )


class SourceReference(BaseModel):
    """
    Represents the origin and provenance of a context item.

    Distinguishes between trusted internal system sources and untrusted external/user sources.
    """
    model_config = ConfigDict(extra="ignore")

    source_id: str = Field(
        ...,
        description="Unique identifier for the source (e.g., URI, file path, window handle, or component ID).",
    )
    source_type: Literal[
        "window", "screen", "file", "url", "conversation", "system", "tool", "custom"
    ] = Field(
        default="window",
        description="Category of the source (window, screen, file, url, conversation, system, tool, custom).",
    )
    title: Optional[str] = Field(
        default=None,
        description="Human-readable title or label for the source (e.g., window title, file name).",
    )
    uri: Optional[str] = Field(
        default=None,
        description="Uniform Resource Identifier or file path referencing the source location.",
    )
    is_trusted: bool = Field(
        default=False,
        description="Whether this source is verified/trusted system content (True) or untrusted user/external content (False).",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when this source reference was recorded.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata dictionary.",
    )

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("source_id cannot be empty or whitespace.")
        return v.strip()


class ContextItem(BaseModel):
    """
    Represents an individual unit of contextual information supplied to the reasoning engine.

    Enforces explicit trust boundaries between system instructions and untrusted external data.
    """
    model_config = ConfigDict(extra="ignore")

    item_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique identifier for this discrete context item.",
    )
    item_type: Literal[
        "window", "screen", "snippet", "turn", "file", "system", "custom"
    ] = Field(
        default="snippet",
        description="Modality or type of context item (window, screen, snippet, turn, file, system, custom).",
    )
    content: str = Field(
        ...,
        description="Textual or serialized content of the context item.",
    )
    source: Optional[SourceReference] = Field(
        default=None,
        description="Provenance and origin reference for this context item.",
    )
    is_trusted: bool = Field(
        default=False,
        description="Explicit trust flag: True for verified system directives, False for untrusted external data.",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when this context item was created.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional key-value metadata.",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ContextItem content cannot be empty or whitespace.")
        return v


class ScreenContext(BaseModel):
    """
    Represents captured screen frame or visual context.

    Privacy-first: screen capture is strictly opt-in and off by default (`capture_enabled=False`).
    Provides deterministic synthetic frame generation for testing and simulation.
    """
    model_config = ConfigDict(extra="ignore")

    capture_enabled: bool = Field(
        default=False,
        description="Privacy toggle: indicates whether screen capture is enabled (opt-in, False by default).",
    )
    frame_id: Optional[str] = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique identifier for the captured frame.",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when the screen frame was captured or generated.",
    )
    width: int = Field(
        default=1920,
        ge=1,
        description="Horizontal screen resolution in pixels (must be >= 1).",
    )
    height: int = Field(
        default=1080,
        ge=1,
        description="Vertical screen resolution in pixels (must be >= 1).",
    )
    format: str = Field(
        default="rgb24",
        description="Image encoding format (e.g., 'rgb24', 'png', 'jpeg', 'synthetic').",
    )
    image_data: Optional[bytes] = Field(
        default=None,
        description="Raw binary frame bytes or encoded image data.",
    )
    is_synthetic: bool = Field(
        default=False,
        description="Flag indicating if the frame was synthetically generated for testing/simulation.",
    )
    visible_text: Optional[str] = Field(
        default=None,
        description="OCR text or visible code elements extracted from the screen frame.",
    )
    active_window: Optional[WindowContext] = Field(
        default=None,
        description="Active operating system window context at the instant of capture.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata (e.g. display index, scaling factor).",
    )

    @classmethod
    def create_synthetic(
        cls,
        width: int = 640,
        height: int = 480,
        capture_enabled: bool = False,
        pattern: str = "test_bars",
        visible_text: Optional[str] = None,
        active_window: Optional[WindowContext] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScreenContext:
        """
        Create a deterministic synthetic test frame for testing and offline simulation.

        Args:
            width: Frame width in pixels (default 640).
            height: Frame height in pixels (default 480).
            capture_enabled: Privacy capture setting (defaults to False).
            pattern: Name of synthetic pattern (e.g. 'test_bars', 'solid', 'checker').
            visible_text: Simulated extracted text or code.
            active_window: Associated window context.
            metadata: Custom metadata dictionary.

        Returns:
            A populated synthetic ScreenContext instance with `is_synthetic=True`.
        """
        # Generate deterministic synthetic dummy bytes (e.g. 3 bytes per pixel RGB)
        raw_header = f"SYNTHETIC:{pattern}:{width}x{height}".encode("ascii")
        # Pad with deterministic repeating byte sequence
        dummy_data = raw_header + b"\xaa\xbb\xcc" * min(1024, max(16, (width * height) // 100))

        meta = {"pattern": pattern, "synthetic_generator": "SDK-9_SyntheticFrameGenerator"}
        if metadata:
            meta.update(metadata)

        return cls(
            capture_enabled=capture_enabled,
            width=width,
            height=height,
            format="synthetic",
            image_data=dummy_data,
            is_synthetic=True,
            visible_text=visible_text or "def synthetic_test_function(): pass",
            active_window=active_window or WindowContext(),
            metadata=meta,
        )


class ConversationTurn(BaseModel):
    """Represents a single message turn in the conversation history."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique identifier for this conversation turn.",
    )
    role: Literal["user", "assistant", "system"] = Field(
        default="user",
        description="Speaker role for the dialogue turn (user, assistant, or system).",
    )
    content: str = Field(
        ...,
        description="Text content of the message turn.",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp when the turn occurred.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata dictionary.",
    )


class ConversationContext(BaseModel):
    """Complete conversational context state for a session at a given instant."""
    model_config = ConfigDict(extra="ignore")

    session_id: str = Field(
        ...,
        description="Unique identifier for the active session.",
    )
    active_window: WindowContext = Field(
        default_factory=WindowContext,
        description="Active operating system window context.",
    )
    history: List[ConversationTurn] = Field(
        default_factory=list,
        description="Chronological list of conversation turns in the sliding window.",
    )
    user_query: str = Field(
        default="",
        description="Latest user query or voice transcript.",
    )
    screen_context: Optional[ScreenContext] = Field(
        default=None,
        description="Optional active screen context frame if captured.",
    )
    context_items: List[ContextItem] = Field(
        default_factory=list,
        description="List of discrete context items (file snippets, system context, etc.).",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of the context snapshot.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional session metadata.",
    )


class VersionedPromptTemplate(BaseModel):
    """Represents an immutable, version-controlled prompt template."""
    model_config = ConfigDict(extra="ignore")

    version: str = Field(
        ...,
        description="Semantic version string (e.g., 'v1.0', 'v1.1', 'v2.0').",
    )
    template: str = Field(
        ...,
        description="Prompt template text containing placeholder variables (e.g. '{query}').",
    )
    variables: List[str] = Field(
        default_factory=list,
        description="List of variable names extracted from placeholders in the template.",
    )
    description: str = Field(
        default="",
        description="Human-readable description of template purpose and behavioral mode.",
    )
    created_at: float = Field(
        default_factory=time.time,
        description="Unix timestamp when the prompt template was registered.",
    )


class ReasoningRequest(BaseModel):
    """
    Structured request payload sent to the reasoning engine.

    Bundles session identifier, user query, optional conversation context snapshot,
    screen context, and discrete context items.
    """
    model_config = ConfigDict(extra="ignore")

    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique identifier for this reasoning request.",
    )
    session_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the session invoking reasoning (cannot be empty).",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="User query or voice transcript to reason about (cannot be empty).",
    )
    context: Optional[ConversationContext] = Field(
        default=None,
        description="Full conversation context snapshot if available.",
    )
    context_items: List[ContextItem] = Field(
        default_factory=list,
        description="List of discrete context items (untrusted snippets, system items, etc.).",
    )
    screen_context: Optional[ScreenContext] = Field(
        default=None,
        description="Optional screen context frame.",
    )
    prompt_version: str = Field(
        default="v1.0",
        description="Version identifier of prompt template to render for reasoning.",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Sampling temperature between 0.0 and 2.0.",
    )
    timestamp: float = Field(
        default_factory=time.time,
        description="Unix timestamp of the request.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional request metadata.",
    )

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id cannot be empty or whitespace.")
        return v.strip()

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("query cannot be empty or whitespace.")
        return v.strip()


class ReasoningResult(BaseModel):
    """Structured decision output produced by the reasoning engine."""
    model_config = ConfigDict(extra="ignore")

    intent: str = Field(
        ...,
        min_length=1,
        description="Classified developer intent (e.g. 'EXPLAIN_ERROR', 'FILE_SEARCH', 'CALCULATE').",
    )
    requires_tool: bool = Field(
        default=False,
        description="Whether an external tool execution is planned/required for this query.",
    )
    planned_tool_name: Optional[str] = Field(
        default=None,
        description="Identifier of the planned tool (e.g. 'file.search', 'file.move', 'calc.evaluate').",
    )
    tool_parameters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extracted key-value argument parameters for tool execution.",
    )
    direct_response: Optional[str] = Field(
        default=None,
        description="Direct conversational response to be spoken or displayed to the user.",
    )
    confidence: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Calibrated decision confidence score between 0.0 and 1.0.",
    )
    reasoning_steps: List[str] = Field(
        default_factory=list,
        description="Step-by-step explainable reasoning trace for observability.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional decision metadata.",
    )

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("intent cannot be empty or whitespace.")
        return v.strip()


class VisionRegion(BaseModel):
    """Represents a visual bounding box region detected on screen."""
    model_config = ConfigDict(extra="ignore")

    region_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())[:8],
        description="Unique identifier for the detected screen region.",
    )
    label: str = Field(
        ...,
        description="Region type classification (e.g., 'editor', 'terminal', 'dialog', 'title_bar').",
    )
    x: int = Field(default=0, ge=0, description="Horizontal pixel offset from top-left.")
    y: int = Field(default=0, ge=0, description="Vertical pixel offset from top-left.")
    width: int = Field(..., ge=1, description="Region width in pixels.")
    height: int = Field(..., ge=1, description="Region height in pixels.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Detection confidence score.")
    text_content: Optional[str] = Field(default=None, description="OCR text extracted from this specific region.")


class VisionResult(BaseModel):
    """Structured output produced by an OCR/Vision processing engine."""
    model_config = ConfigDict(extra="ignore")

    frame_id: str = Field(..., description="ID of the screen frame analyzed.")
    extracted_text: str = Field(default="", description="Consolidated textual content extracted across the frame.")
    regions: List[VisionRegion] = Field(default_factory=list, description="List of segmented visual regions.")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0, description="Overall OCR confidence score.")
    processing_time_ms: float = Field(default=0.0, ge=0.0, description="Elapsed processing latency in milliseconds.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary additional vision metadata.")


class LLMResponse(BaseModel):
    """Standardized response container returned by LLM client adapters."""
    model_config = ConfigDict(extra="ignore")

    content: str = Field(..., description="Raw text response generated by the model.")
    raw_json: Optional[Dict[str, Any]] = Field(default=None, description="Parsed JSON dictionary if output is JSON.")
    structured_data: Optional[Any] = Field(default=None, description="Validated Pydantic model instance if structured output requested.")
    model_name: str = Field(default="mock-llm-v1", description="Identifier of the model that generated the response.")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Inference latency in milliseconds.")
    retries_used: int = Field(default=0, ge=0, description="Number of retry attempts required.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata from LLM invocation.")


class CaptureConfig(BaseModel):
    """Configuration governing opt-in screen capture sampling and dimension/byte bounds."""
    model_config = ConfigDict(extra="ignore")

    capture_enabled: bool = Field(default=False, description="Master privacy toggle; off by default.")
    max_fps: float = Field(default=2.0, gt=0.0, le=30.0, description="Maximum permitted frame capture frequency (sampling rate limit).")
    max_width: int = Field(default=1920, ge=64, description="Maximum permitted screen width in pixels.")
    max_height: int = Field(default=1080, ge=64, description="Maximum permitted screen height in pixels.")
    max_bytes: int = Field(default=2_000_000, ge=1024, description="Maximum permitted raw byte payload size limit (e.g. 2MB).")
    downscale_on_overflow: bool = Field(default=True, description="Whether to downscale dimensions if incoming frame exceeds limits.")


class ContextBuilderConfig(BaseModel):
    """Configuration governing bounded context assembly, token budgeting, and stale filtering."""
    model_config = ConfigDict(extra="ignore")

    token_budget: int = Field(default=2048, ge=64, description="Maximum approximate token allocation for prompt context.")
    max_history_turns: int = Field(default=20, ge=1, description="Maximum number of conversation dialogue turns to retain.")
    stale_threshold_seconds: float = Field(default=300.0, gt=0.0, description="TTL in seconds after which general context items are considered stale.")
    screen_stale_seconds: float = Field(default=60.0, gt=0.0, description="TTL in seconds after which screen frames are considered stale.")
    relevance_threshold: float = Field(default=0.05, ge=0.0, le=1.0, description="Minimum relevance score for context inclusion.")


__all__ = [
    "WindowContext",
    "SourceReference",
    "ContextItem",
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
]
