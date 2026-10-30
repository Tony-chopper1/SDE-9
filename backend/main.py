
"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.sessions import router as session_router
from backend.schemas.api_schemas import (
    StandardResponse,
    ChatRequest,
)

app = FastAPI(
    title="SDK-9 Voicebot API",
    version="1.0.0",
    description="API Gateway for AI Voice Co-Pilot",
)

# Middleware Stack
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
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
