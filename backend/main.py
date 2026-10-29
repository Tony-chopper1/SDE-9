"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi - Task W5)
"""
from typing import Dict
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas.api_schemas import (
    StandardResponse,
    CreateSessionRequest,
    SessionData,
    ChatRequest,
    ChatResponseData,
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

# In-memory session store
sessions_db: Dict[str, SessionData] = {}


@app.get("/api/v1/health", response_model=StandardResponse)
def health_check():
    """Health check endpoint."""
    return StandardResponse(
        success=True,
        data={"status": "healthy", "service": "sdk-9-voicebot", "mock_mode": True},
    )


# ----------------------------------------------------------------------
# TODO (Apeksha KT - Task W5):
# Complete the route implementations below and add middleware/launcher.
# ----------------------------------------------------------------------

@app.post("/api/v1/sessions", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_session(req: CreateSessionRequest):
    """
    TODO: Apeksha KT - Generate a new session_id, store in sessions_db, and return standard response.
    """
    raise HTTPException(status_code=501, detail="TODO: Apeksha KT to implement create_session")


@app.get("/api/v1/sessions/{session_id}", response_model=StandardResponse)
def get_session(session_id: str):
    """
    TODO: Apeksha KT - Retrieve session from sessions_db or return 404 if not found.
    """
    raise HTTPException(status_code=501, detail="TODO: Apeksha KT to implement get_session")


@app.post("/api/v1/ai/chat", response_model=StandardResponse)
def chat_endpoint(req: ChatRequest):
    """
    TODO: Apeksha KT - Validate input message, route to reasoning, and return ChatResponseData.
    """
    raise HTTPException(status_code=501, detail="TODO: Apeksha KT to implement chat_endpoint")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
