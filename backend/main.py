
"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Week 3: Health aggregation, rate limiting and request tracing.
"""

import importlib.util
import logging
import os
import time
from collections import deque
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.sessions import router as session_router
from backend.api.events import router as event_router
from backend.api.pipeline import router as pipeline_router
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
    version="1.1.0",
    description="API Gateway for AI Voice Co-Pilot",
)

app.state.mock_mode = mock_mode_value in {"true", "1", "yes"}

app.state.rate_limit_requests = {}
app.state.rate_limit_max = 120
app.state.rate_limit_window = 60


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
                request.state,
                "request_id",
                correlation_id,
            ),
        },
    )


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

    response = None

    if request.url.path == "/api/v1/pipeline/process":
        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        now = time.monotonic()
        requests = app.state.rate_limit_requests.setdefault(
            client_ip,
            deque(),
        )

        window = app.state.rate_limit_window

        while requests and now - requests[0] >= window:
            requests.popleft()

        if len(requests) >= app.state.rate_limit_max:
            response = create_error_response(
                request=request,
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
                message="Too many pipeline requests. Please try again later.",
                retryable=True,
            )
            response.headers["Retry-After"] = str(window)
        else:
            requests.append(now)

    if response is None:
        response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000

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
            "location": [
                str(part) for part in item.get("loc", [])
            ],
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
app.include_router(event_router)
app.include_router(pipeline_router)


def get_component_health():
    components = {
        "audio": "packages.audio",
        "speech_to_text": "packages.speech_to_text",
        "context_reasoning": "packages.context_reasoning",
        "agentic_workflow": "packages.agentic_workflow",
        "pipeline": "backend.services.pipeline_service",
    }

    results = {}

    for name, module_name in components.items():
        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False

        results[name] = (
            "healthy" if available else "unavailable"
        )

    return results


HEALTH_EXAMPLE = {
    "success": True,
    "data": {
        "status": "healthy",
        "service": "sdk-9-voicebot",
        "mock_mode": True,
        "components": {
            "audio": "healthy",
            "speech_to_text": "healthy",
            "context_reasoning": "healthy",
            "agentic_workflow": "healthy",
            "pipeline": "healthy",
        },
    },
    "error": None,
    "timestamp": 1795590000.0,
}


READY_EXAMPLE = {
    "success": True,
    "data": {
        "status": "ready",
        "service": "sdk-9-voicebot",
        "mock_mode": True,
        "components": {
            "audio": "healthy",
            "speech_to_text": "healthy",
            "context_reasoning": "healthy",
            "agentic_workflow": "healthy",
            "pipeline": "healthy",
        },
    },
    "error": None,
    "timestamp": 1795590000.0,
}


ERROR_EXAMPLE = {
    "success": False,
    "data": None,
    "error": {
        "code": "HTTP_501",
        "message_safe_for_user": "This feature is not implemented yet",
        "retryable": False,
        "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
        "details_redacted": None,
    },
    "timestamp": 1795590000.0,
}


@app.get(
    "/api/v1/health",
    response_model=StandardResponse,
    summary="Check service health",
    description="Checks the availability of backend components.",
    responses={
        200: {
            "description": "Health status",
            "content": {
                "application/json": {
                    "example": HEALTH_EXAMPLE,
                }
            },
        },
    },
)
def health_check():
    components = get_component_health()

    all_healthy = all(
        status == "healthy"
        for status in components.values()
    )

    return StandardResponse(
        success=all_healthy,
        data={
            "status": "healthy" if all_healthy else "degraded",
            "service": "sdk-9-voicebot",
            "mock_mode": app.state.mock_mode,
            "components": components,
        },
    )


@app.get(
    "/api/v1/ready",
    response_model=StandardResponse,
    summary="Check API readiness",
    description="Checks whether all required components are ready.",
    responses={
        200: {
            "description": "Readiness status",
            "content": {
                "application/json": {
                    "example": READY_EXAMPLE,
                }
            },
        },
    },
)
@app.get(
    "/ready",
    response_model=StandardResponse,
    summary="Check API readiness",
    description="Checks whether all required components are ready.",
    responses={
        200: {
            "description": "Readiness status",
            "content": {
                "application/json": {
                    "example": READY_EXAMPLE,
                }
            },
        },
    },
)
def readiness_check():
    components = get_component_health()

    all_ready = all(
        status == "healthy"
        for status in components.values()
    )

    return StandardResponse(
        success=all_ready,
        data={
            "status": "ready" if all_ready else "not_ready",
            "service": "sdk-9-voicebot",
            "mock_mode": app.state.mock_mode,
            "components": components,
        },
    )


@app.post(
    "/api/v1/ai/chat",
    response_model=StandardResponse,
    summary="Send a chat message",
    description="Chat endpoint reserved for a future implementation.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "chat_request": {
                            "summary": "Send a message",
                            "value": {
                                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                                "message": "Hello, how can you help me?",
                                "context_id": None,
                            },
                        }
                    }
                }
            }
        }
    },
    responses={
        200: {
            "description": "Example of the standard successful chat response format",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "request_id": "123e4567-e89b-12d3-a456-426614174001",
                            "status": "completed",
                            "response": "Example assistant response",
                            "requires_approval": False,
                        },
                        "error": None,
                        "timestamp": 1795590000.0,
                    }
                }
            },
        },
        501: {
            "description": "Chat implementation is pending",
            "content": {
                "application/json": {
                    "example": ERROR_EXAMPLE,
                }
            },
        },
        422: {
            "description": "Invalid chat request",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message_safe_for_user": "Request validation failed",
                            "retryable": False,
                            "correlation_id": "123e4567-e89b-12d3-a456-426614174001",
                            "details_redacted": {
                                "errors": [
                                    {
                                        "location": ["body", "message"],
                                        "type": "missing",
                                    }
                                ]
                            },
                        },
                        "timestamp": 1795590000.0,
                    }
                }
            },
        },
    },
)
def chat_endpoint(req: ChatRequest):
    raise HTTPException(
        status_code=501,
        detail="Chat endpoint implementation pending",
    )


if __name__ == "__main__":
    from backend.launcher import run_server

    run_server()
