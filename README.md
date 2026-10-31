# SDK-9 — AcademiaAI AI Voicebot

## Project Overview

SDK-9 is a six-member team project that develops an AI Voicebot using modular components. The application must support mock mode without requiring paid API credentials.

## Technology Stack

- Backend: Python and FastAPI
- Frontend: React and TypeScript
- Version control: Git and GitHub
- Testing: Automated unit and integration tests

## Team Modules

|     Member    |     Responsibility    |       Feature Branch      |
|---------------|-----------------------|---------------------------|
|    Satwik A   |     Audio and VAD     |     feature/audio-vad     |
| Pavanchand RM |     Speech-to-Text    |  feature/speech-to-text   |
| Praveen Kumar | Context and Reasoning | feature/context-reasoning |
| Chiranthan Rk |    Agentic Workflow   | feature/agentic-workflow  |
|   Apeksha KT  |         Backend       |  feature/backend-fastapi  |
|   Spoorthi V  |         Frontend      |     feature/frontend      |

## Repository Structure

- `docs/` — Architecture, integration contracts and development workflow
- `packages/audio/` — Audio processing and VAD
- `packages/speech-to-text/` — Speech transcription
- `packages/context-reasoning/` — Context and reasoning
- `packages/agentic-workflow/` — Workflow execution
- `backend/` — FastAPI application
- `frontend/` — React and TypeScript application
- `tests/` — Automated tests

## Branch Strategy

- `main` — Stable, tested releases
- `develop` — Shared integration branch
- `feature/*` — Individual development branches

Do not push feature work directly to `main` or `develop`. Submit pull requests targeting `develop` and follow the review process documented in `docs/development-workflow.md`.

## Getting Started

1. Clone the repository.
2. Configure your Git identity.
3. Update your local `develop` branch.
4. Create or switch to your assigned feature branch.
5. Follow the module-specific setup instructions once they are documented.
6. Run relevant tests before committing and pushing changes.

## Shared Contracts

Read `docs/architecture.md`, `docs/integration-contracts.md`, and `docs/development-workflow.md` before implementing module interfaces.

## Security

Never commit API keys, `.env` files, private recordings, or personal data. Use mock mode for development when real provider credentials are unavailable.
