# Backend Service (FastAPI)

**Owner**: Apeksha K T (`feature/backend-fastapi`)

## Responsibilities
- REST and WebSocket API gateway adhering to API specifications.
- Middleware stack: CORS, request logging, error envelopes.
- Session management endpoints (`/api/v1/sessions`).
- Orchestration and service launcher.

## Running the Backend
```bash
uvicorn backend.main:app --reload --port 8000
```
