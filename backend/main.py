"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""

import logging
import time
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.api.sessions import router as session_router
from backend.schemas.api_schemas import (
    StandardResponse,
    ChatRequest,
)

logger = logging.getLogger("backend.gateway")

app = FastAPI(
    title="SDK-9 Voicebot API",
    version="1.0.0",
    description="API Gateway for AI Voice Co-Pilot",
)

# Middleware Stack
# 1. Request logging middleware: logs method, path, status, and response time
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next) -> Response:
    """
    Lightweight request logging middleware that records HTTP method,
    path, response status, and duration in milliseconds.
    """
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        "%s %s - %d (%.2fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    return response

# 2. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session management routes
app.include_router(session_router)


@app.get("/api/v1/health", response_model=StandardResponse)
def health_check():
    """Health check endpoint."""
    return StandardResponse(
        success=True,
        data={
            "status": "healthy",
            "service": "sdk-9-voicebot",
            "mock_mode": True,
        },
    )


@app.post("/api/v1/ai/chat", response_model=StandardResponse)
def chat_endpoint(req: ChatRequest):
    """
    TODO: Implement chat integration with the reasoning module.
    """
    raise HTTPException(
        status_code=501,
        detail="Chat endpoint implementation pending",
    )


if __name__ == "__main__":
    from backend.launcher import run_server

    run_server()
