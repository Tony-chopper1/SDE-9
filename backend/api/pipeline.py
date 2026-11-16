
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

from fastapi import APIRouter, Header, HTTPException, Request
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


@router.post("/pipeline/process", response_model=StandardResponse)
def process_pipeline(
    payload: PipelineRequest,
    request: Request,
    x_api_key: str | None = Header(default=None),
):
    """Process audio through the complete mock pipeline."""

    # 1. Authorization boundary
    verify_pipeline_authorization(x_api_key)

    # 2. Verify session
    session = session_service.get_session(payload.session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session not found",
        )

    # 3. Decode optional Base64 audio
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

    # 4. Execute mock pipeline
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
