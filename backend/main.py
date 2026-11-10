"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""

import logging
import os
import time
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.sessions import router as session_router
from backend.schemas.api_schemas import (
    StandardResponse,
    APIError,
    ChatRequest,
)

load_dotenv()

mock_mode_value = os.getenv("MOCK_MODE", "true").strip().lower()

if mock_mode_value not in {"true", "1", "yes", "false", "0", "no"}:
    raise ValueError("MOCK_MODE must be true or false")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend.gateway")

app = FastAPI(
    title="SDK-9 Voicebot API",
    version="1.0.0",
    description="API Gateway for AI Voice Co-Pilot",
)

app.state.mock_mode = mock_mode_value in {"true", "1", "yes"}


@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next,
) -> Response:
    start_time = time.perf_counter()

    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    correlation_id = (
        request.headers.get("X-Correlation-ID") or request_id
    )

    request.state.request_id = request_id
    request.state.correlation_id = correlation_id

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    logger.info(
        "request_completed method=%s path=%s status=%s "
        "duration_ms=%.2f request_id=%s correlation_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        correlation_id,
    )

    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id

    return response


def create_error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict | None = None,
):
    correlation_id = getattr(
        request.state,
        "correlation_id",
        str(uuid4()),
    )

    error = APIError(
        code=code,
        message_safe_for_user=message,
        retryable=retryable,
        correlation_id=correlation_id,
        details_redacted=details,
    )

    return JSONResponse(
        status_code=status_code,
        content=StandardResponse(
            success=False,
            error=error,
        ).model_dump(mode="json"),
        headers={
            "X-Correlation-ID": correlation_id,
            "X-Request-ID": getattr(
                request.state, "request_id", correlation_id
            ),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    safe_messages = {
        400: "Bad request",
        401: "Authentication required",
        403: "Access denied",
        404: "Resource not found",
        409: "Request conflicts with the current resource state",
        422: "Request validation failed",
        429: "Too many requests",
        501: "This feature is not implemented yet",
    }

    return create_error_response(
        request=request,
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=safe_messages.get(
            exc.status_code,
            "The request could not be completed",
        ),
        retryable=exc.status_code == 429 or exc.status_code >= 500,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    safe_errors = [
        {
            "location": [str(part) for part in item.get("loc", [])],
            "type": item.get("type", "validation_error"),
        }
        for item in exc.errors()
    ]

    return create_error_response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        retryable=False,
        details={"errors": safe_errors},
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    correlation_id = getattr(
        request.state,
        "correlation_id",
        "unknown",
    )

    logger.error(
        "unexpected_server_error correlation_id=%s",
        correlation_id,
    )

    return create_error_response(
        request=request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred",
        retryable=True,
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(session_router)


@app.get("/api/v1/health", response_model=StandardResponse)
def health_check():
    return StandardResponse(
        success=True,
        data={
            "status": "healthy",
            "service": "sdk-9-voicebot",
            "mock_mode": app.state.mock_mode,
        },
    )


@app.get("/api/v1/ready", response_model=StandardResponse)
@app.get("/ready", response_model=StandardResponse)
def readiness_check():
    return StandardResponse(
        success=True,
        data={
            "status": "ready",
            "service": "sdk-9-voicebot",
            "mock_mode": app.state.mock_mode,
        },
    )


@app.post("/api/v1/ai/chat", response_model=StandardResponse)
def chat_endpoint(req: ChatRequest):
    raise HTTPException(
        status_code=501,
        detail="Chat endpoint implementation pending",
    )


if __name__ == "__main__":
    from backend.launcher import run_server

    run_server()