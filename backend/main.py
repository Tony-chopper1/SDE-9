"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
Owner: Apeksha KT (feature/backend-fastapi)
"""
import time
from typing import Dict
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas.api_schemas import (
    StandardResponse,
    CreateSessionRequest,
    SessionData,
    ChatRequest,
    ChatResponseData,
    APIError,
)

app = FastAPI(
    title="SDK-9 Voicebot API",
    version="1.0.0",
    description="API Gateway for AI Voice Co-Pilot",
)

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
    return StandardResponse(
        success=True,
        data={"status": "healthy", "service": "sdk-9-voicebot", "mock_mode": True},
    )


@app.post("/api/v1/sessions", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
def create_session(req: CreateSessionRequest):
    session_id = f"session-{int(time.time() * 1000)}"
    session = SessionData(session_id=session_id)
    sessions_db[session_id] = session

    return StandardResponse(
        success=True,
        data=session,
    )


@app.get("/api/v1/sessions/{session_id}", response_model=StandardResponse)
def get_session(session_id: str):
    session = sessions_db.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SESSION_NOT_FOUND",
                "message": f"Session '{session_id}' not found.",
                "request_id": f"req-{int(time.time() * 1000)}",
            },
        )
    return StandardResponse(success=True, data=session)


@app.post("/api/v1/ai/chat", response_model=StandardResponse)
def chat_endpoint(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REQUEST",
                "message": "Message field cannot be empty.",
                "request_id": f"req-{int(time.time() * 1000)}",
            },
        )

    return StandardResponse(
        success=True,
        data=ChatResponseData(
            request_id=f"req-{int(time.time() * 1000)}",
            status="completed",
            response=f"AI received your message: '{req.message}'",
            requires_approval=False,
        ),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
