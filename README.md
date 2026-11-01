# SDK-9 - AcademiaAI AI Voicebot

## Project Overview

SDK-9 is a six-member team project that develops an AI Voicebot using modular components. The application supports mock mode without requiring paid API credentials.

## Technology Stack

- Backend: Python and FastAPI
- Frontend: React and TypeScript
- Version Control: Git and GitHub
- Testing: Pytest and automated integration tests

## Team Modules

| Member | Responsibility | Feature Branch |
|---|---|---|
| Satwik A | Audio and VAD | `feature/audio-vad` |
| Pavanchand RM | Speech-to-Text | `feature/speech-to-text` |
| Praveen Kumar | Context and Reasoning | `feature/context-reasoning` |
| Chiranthan Rk | Agentic Workflow | `feature/agentic-workflow` |
| Apeksha KT | Backend | `feature/backend-fastapi` |
| Spoorthi V | Frontend | `feature/frontend` |

## Repository Structure

- `docs/` - Architecture, integration contracts and development workflow
- `packages/audio/` - Audio processing and VAD
- `packages/speech-to-text/` - Speech transcription
- `packages/context-reasoning/` - Context and reasoning
- `packages/agentic-workflow/` - Workflow execution
- `backend/` - FastAPI backend application
  - `api/` - API route handlers
  - `schemas/` - Request and response models
  - `services/` - Business logic and session management
  - `tests/` - Backend automated tests
  - `main.py` - FastAPI application entry point
  - `launcher.py` - Backend service launcher
- `frontend/` - React and TypeScript application

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Tony-chopper1/SDK-9.git
cd SDK-9
```

### 2. Create and Activate Virtual Environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Start the Backend Server

```powershell
python -m backend.launcher
```

The backend runs on port `8000` by default.

### 5. Access API Documentation

Open the following URL in your browser:

http://127.0.0.1:8000/docs

The Swagger UI allows you to explore and test the available API endpoints.

## Backend API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health` | Check backend health |
| POST | `/api/v1/sessions` | Create a session |
| GET | `/api/v1/sessions` | Retrieve all sessions |
| GET | `/api/v1/sessions/{session_id}` | Retrieve a session |
| POST | `/api/v1/sessions/{session_id}/pause` | Pause a session |
| POST | `/api/v1/sessions/{session_id}/stop` | Stop a session |

The AI chat endpoint is currently reserved for integration with the context and reasoning module.

## Testing

Run backend automated tests:

```powershell
python -m pytest backend/tests/ -v
```

Run tests with code coverage:

```powershell
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

### Backend Test Results

Latest verified test results:

- Total tests: 22
- Passed: 22
- Failed: 0
- Overall code coverage: 98%

## Branch Strategy

- `main` - Stable, tested releases
- `develop` - Shared integration branch
- `feature/*` - Individual development branches

Do not push feature work directly to `main` or `develop`. Submit pull requests targeting `develop` and follow the review process documented in `docs/development-workflow.md`.

## Shared Contracts

Read the following documents before implementing module interfaces:

- `docs/architecture.md`
- `docs/integration-contracts.md`
- `docs/development-workflow.md`

## Security

- Never commit API keys or credentials.
- Do not commit `.env` files.
- Do not upload private recordings or personal data.
- Use mock mode during development when real provider credentials are unavailable.

