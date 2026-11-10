from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import time


class APIError(BaseModel):
    code: str
    message: str
    request_id: str
    details: Optional[Dict[str, Any]] = None


class StandardResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    error: Optional[APIError] = None
    timestamp: float = Field(default_factory=time.time)


class CreateSessionRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None


class SessionData(BaseModel):
    session_id: str
    status: str = "active"
    created_at: float = Field(default_factory=time.time)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    context_id: Optional[str] = None


class ChatResponseData(BaseModel):
    request_id: str
    status: str = "completed"
    response: str
    requires_approval: bool = False
