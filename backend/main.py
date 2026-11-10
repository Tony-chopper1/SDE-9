
"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""

import os
import logging
import time
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.sessions import router as session_router
from backend.api.events import router as event_router
from backend.schemas.api_schemas import (
    StandardResponse,
    APIError,
    ChatRequest,
)

# Load environment variables from .env
load_dotenv()

# Validate mock mode configuration
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


# Request logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000.0

    logger.info(
        "request_completed method=%s path=%s status=%s "
        "duration_ms=%.2f request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
    )

    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    response.headers["X-Request-ID"] = request_id

    return response


# HTTP exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", str(uuid4()))

    error = APIError(
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        request_id=request_id,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=StandardResponse(
            success=False,
            error=error,
        ).model_dump(mode="json"),
    )


# Request validation exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    request_id = getattr(request.state, "request_id", str(uuid4()))

    safe_errors = [
        {
            "loc": item.get("loc"),
            "type": item.get("type"),
            "msg": item.get("msg"),
        }
        for item in exc.errors()
    ]

    error = APIError(
        code="VALIDATION_ERROR",
        message="Request validation failed",
        request_id=request_id,
        details={"errors": safe_errors},
    )

    return JSONResponse(
        status_code=422,
        content=StandardResponse(
            success=False,
            error=error,
        ).model_dump(mode="json"),
    )


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Register API routers
app.include_router(session_router)
app.include_router(event_router)


# Health check endpoint
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


# AI chat endpoint
@app.post("/api/v1/ai/chat", response_model=StandardResponse)
def chat_endpoint(req: ChatRequest):
    raise HTTPException(
        status_code=501,
        detail="Chat endpoint implementation pending",
    )


# Application entry point
if __name__ == "__main__":
    from backend.launcher import run_server

    run_server()
