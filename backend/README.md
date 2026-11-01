# Backend Service (FastAPI)

**Owner**: Apeksha K T (`feature/backend-fastapi`)

## Responsibilities
- REST and WebSocket API gateway adhering to API specifications.
- Middleware stack: CORS, Request Logging middleware, error envelopes.
- Session management endpoints (`/api/v1/sessions`).
- Orchestration and service launcher (`backend/launcher.py`).

---

## Middleware Stack

1. **Request Logging Middleware**:
   - Intercepts all incoming HTTP requests.
   - Measures response duration with microsecond precision.
   - Logs request method, path, HTTP status code, and latency in milliseconds (e.g. `POST /api/v1/sessions - 201 (2.50ms)`).
   - Injects the latency into the response headers via `X-Response-Time`.
2. **CORS Middleware**:
   - Configured to allow all origins, methods, and headers for development and multi-client integration.

---

## Session Management Endpoints

All session endpoints are prefixed under `/api/v1/sessions`:

| Method | Endpoint | Description | Request Body | Status Code |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/sessions` | Create a new session | `{"user_id": "string"}` (optional) | `201 Created` |
| `GET` | `/api/v1/sessions` | Retrieve all sessions | *None* | `200 OK` |
| `GET` | `/api/v1/sessions/{session_id}` | Get session details by UUID | *None* | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/sessions/{session_id}/pause` | Pause an active session | *None* | `200 OK` / `404 Not Found` |
| `POST` | `/api/v1/sessions/{session_id}/stop` | Stop / complete a session | *None* | `200 OK` / `404 Not Found` |

### Other Endpoints

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Service health status | `200 OK` |
| `POST` | `/api/v1/ai/chat` | AI conversation endpoint (staged for reasoning module) | `501 Not Implemented` |

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

---

## Service Launcher

The dedicated launcher script (`backend/launcher.py`) orchestrates configuration from environment variables (`.env`) and command-line flags.

### Launching the Backend

Using the launcher script:
```bash
# Default startup (host: 0.0.0.0, port: 8000, reload: True in dev)
python backend/launcher.py

# With custom parameters
python backend/launcher.py --port 8080 --host 127.0.0.1 --reload
```

Using Uvicorn directly:
```bash
uvicorn backend.main:app --reload --port 8000
```

### Environment Variables (.env)
- `HOST`: Host address to bind (default: `0.0.0.0`)
- `PORT`: Port to listen on (default: `8000`)
- `ENVIRONMENT`: Environment mode (`development`, `staging`, `production`)
- `RELOAD`: Enable auto-reload on code change (`true` / `false`)
- `MOCK_MODE`: Run in mock mode without external API dependencies (`true` / `false`)
- `LOG_LEVEL`: Logging verbosity (`info`, `debug`, `warning`, `error`)

---

## Running Automated Tests

All backend unit and integration tests are colocated inside `backend/tests/` to prevent merge conflicts with other module teams.

### Run Backend Tests:
```bash
pytest backend/tests/
```

### Run Backend Tests with Code Coverage:
```bash
pytest --cov=backend backend/tests/
```
*(Target: >80% coverage; currently achieves **98% coverage**)*

### Run the Entire Project Test Suite:
```bash
pytest
```
