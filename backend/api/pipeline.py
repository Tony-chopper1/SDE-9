
"""
SDK-9 Week 3 - Audio Pipeline API.

Receives mock audio and coordinates the existing
Audio, Speech-to-Text, Reasoning and Workflow modules.
Includes an optional local API-key authorization boundary.
"""

import base64
import binascii
import hmac
import os
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Body
from pydantic import BaseModel, Field

from backend.api.sessions import session_service
from backend.schemas.api_schemas import StandardResponse
from backend.services.pipeline_service import pipeline_service


router = APIRouter(
    prefix="/api/v1",
    tags=["Pipeline"],
)


class PipelineRequest(BaseModel):
    session_id: UUID
    audio_base64: str | None = Field(
        default=None,
        max_length=1400000,
        description="Optional Base64-encoded mock audio",
    )


PIPELINE_RESPONSE_EXAMPLE = {
    "success": True,
    "data": {
        "session_id": "123e4567-e89b-12d3-a456-426614174000",
        "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
        "mock_mode": True,
        "audio": {
            "received_bytes": 6400,
            "frame_bytes": 320,
            "speech_detected": True,
            "vad_confidence": 1.0,
        },
        "transcription": {
            "text": "No speech detected",
            "segments": [],
        },
        "reasoning": {
            "intent": "general",
            "requires_tool": False,
            "planned_tool_name": None,
            "tool_parameters": None,
            "direct_response": "Mock response",
            "confidence": 0.95,
        },
        "workflow": {
            "status": "not_required",
            "tool_name": None,
            "permission_granted": False,
            "approval_required": False,
            "plan_created": False,
        },
    },
    "error": None,
    "timestamp": 1795590000.0,
}

ERROR_EXAMPLE = {
    "success": False,
    "data": None,
    "error": {
        "code": "HTTP_400",
        "message_safe_for_user": "Bad request",
        "retryable": False,
        "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
        "details_redacted": None,
    },
    "timestamp": 1795590000.0,
}

AUTH_ERROR_EXAMPLE = {
    **ERROR_EXAMPLE,
    "error": {
        **ERROR_EXAMPLE["error"],
        "code": "HTTP_401",
        "message_safe_for_user": "Authentication required",
    },
}

NOT_FOUND_ERROR_EXAMPLE = {
    **ERROR_EXAMPLE,
    "error": {
        **ERROR_EXAMPLE["error"],
        "code": "HTTP_404",
        "message_safe_for_user": "Session not found",
    },
}

RATE_LIMIT_ERROR_EXAMPLE = {
    **ERROR_EXAMPLE,
    "error": {
        **ERROR_EXAMPLE["error"],
        "code": "HTTP_429",
        "message_safe_for_user": "Too many requests",
        "retryable": True,
    },
}

VALIDATION_ERROR_EXAMPLE = {
    **ERROR_EXAMPLE,
    "error": {
        **ERROR_EXAMPLE["error"],
        "code": "HTTP_422",
        "message_safe_for_user": "Invalid request body",
    },
}


def verify_pipeline_authorization(api_key: str | None) -> None:
    """
    Verify the optional local pipeline API key.

    When PIPELINE_API_KEY is not configured, local mock
    development remains accessible without authentication.
    """

    expected_key = os.getenv("PIPELINE_API_KEY", "")

    if not expected_key:
        return

    if not api_key or not hmac.compare_digest(
        api_key,
        expected_key,
    ):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )


@router.post(
    "/pipeline/process",
    response_model=StandardResponse,
    summary="Process audio through the mock pipeline",
    description=(
        "Processes optional Base64 audio through Audio/VAD, "
        "Speech-to-Text, Context/Reasoning and Agentic Workflow. "
        "The mock pipeline does not execute tools."
    ),
    responses={
        200: {
            "description": "Pipeline processed successfully",
            "content": {
                "application/json": {
                    "example": PIPELINE_RESPONSE_EXAMPLE,
                }
            },
        },
        400: {
            "description": "Invalid audio input",
            "content": {
                "application/json": {
                    "example": ERROR_EXAMPLE,
                }
            },
        },
        401: {
            "description": "Authentication required when API key is configured",
            "content": {
                "application/json": {
                    "example": AUTH_ERROR_EXAMPLE,
                }
            },
        },
        404: {
            "description": "Session not found",
            "content": {
                "application/json": {
                    "example": NOT_FOUND_ERROR_EXAMPLE,
                }
            },
        },
        429: {
            "description": "Pipeline rate limit exceeded",
            "content": {
                "application/json": {
                    "example": RATE_LIMIT_ERROR_EXAMPLE,
                }
            },
        },
        422: {
            "description": "Invalid request body",
            "content": {
                "application/json": {
                    "example": VALIDATION_ERROR_EXAMPLE,
                }
            },
        },
    },
)
def process_pipeline(
    payload: PipelineRequest = Body(
        ...,
        openapi_examples={
            "mock_audio_request": {
                "summary": "Process mock audio",
                "value": {
                    "session_id": "123e4567-e89b-12d3-a456-426614174000",
                    "audio_base64": "AQEBAQ==",
                },
            },
            "without_audio": {
                "summary": "Process using default mock audio",
                "value": {
                    "session_id": "123e4567-e89b-12d3-a456-426614174000",
                },
            },
        },
    ),
    request: Request = None,
    x_api_key: str | None = Header(default=None),
):
    """Process audio through the complete mock pipeline."""

    verify_pipeline_authorization(x_api_key)

    session = session_service.get_session(payload.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    audio_data = None

    if payload.audio_base64 is not None:
        try:
            audio_data = base64.b64decode(
                payload.audio_base64,
                validate=True,
            )
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid Base64 audio input",
            )

        if not audio_data:
            raise HTTPException(
                status_code=400,
                detail="Audio input cannot be empty",
            )

    try:
        result = pipeline_service.process_audio(
            session_id=payload.session_id,
            audio_data=audio_data,
            correlation_id=getattr(
                request.state,
                "correlation_id",
                None,
            ),
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Audio processing failed",
        )

    return StandardResponse(
        success=True,
        data=result,
    )
