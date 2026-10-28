"""
SDK-9 AI Voice Co-Pilot - Backend Gateway
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SDK-9 Voicebot API",
    version="1.0.0",
    description="API Gateway for AI Voice Co-Pilot"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
def health_check():
    return {"status": "ok", "service": "sdk-9-voicebot", "mock_mode": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
