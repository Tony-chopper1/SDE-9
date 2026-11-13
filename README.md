# SDK-9 — AcademiaAI Voicebot & Voice Co-Pilot

> **Team SDE-9** · Final Delivery: `projects/sde-9-voicebot/` (Branch: `team/sde-9-voicebot`)  
> Comprehensive voice-driven AI co-pilot designed for real-time speech interaction, contextual screen reasoning, multi-step agentic workflows, and safe action execution.

---

## 🏛️ High-Level System Architecture

```mermaid
flowchart TD
    subgraph Client["Frontend Client (React 18 + TypeScript)"]
        UI["Voice Studio UI\n(AppShell, Waveform, Virtualized Timeline)"]
        ClientAPI["Typed API Client\n(Zero 'any' Types)"]
        UI --> ClientAPI
    end

    subgraph Gateway["Backend Gateway (FastAPI)"]
        Server["FastAPI REST & WebSocket Gateway\n(CORS, Latency Logging Middleware)"]
        Sessions["Session Management Service\n(/api/v1/sessions CRUD)"]
        Launcher["Service Launcher & Config Orchestrator\n(backend/launcher.py)"]
        Server --> Sessions
    end

    subgraph AudioPipeline["Audio & Speech Pipeline"]
        Mic["Mock Microphone Source\n(16kHz 16-bit Mono PCM)"] -->|"AudioFrame Stream"| VAD["Voice Activity Detection\n(Energy & Simple VAD)"]
        VAD -->|"Speech Activity Events"| STT["Speech-to-Text Engine\n(FakeTranscriber & Confidence Scorer)"]
        STT -->|"Partial & Final Segments"| Accumulator["Segment Accumulator State Machine\n(Out-of-Order Sorting, 0 Leaks)"]
    end

    subgraph Intelligence["Cognitive & Agentic Workflow Engine"]
        Context["Context Manager\n(Active Window, Snippets, Turn History)"]
        Prompt["Versioned Prompt Manager\n(Template Registry & Substitution)"]
        Reasoning["Mock Reasoning Engine\n(Intent Classification & Tool Triggering)"]
        Workflow["Agentic Workflow State Machine\n(Safety Gates: Levels A, B, C, D)"]
        Tools["Mock Tool Executor\n(file.search, file.move, calc.evaluate)"]
        
        Context --> Reasoning
        Prompt --> Reasoning
        Reasoning --> Workflow
        Workflow -->|"Execute Action"| Tools
    end

    ClientAPI <-->|"HTTP / REST"| Server
    Accumulator -->|"Synthesized Utterance"| Context
    Workflow -->|"Action Plan & Status"| Server
```

---

## 📁 Monorepo Directory Structure

```
SDK-9/
├── backend/                               # FastAPI Backend Gateway (Apeksha KT)
│   ├── api/                               # Session endpoints (/api/v1/sessions)
│   ├── schemas/                           # Pydantic request & response schemas
│   ├── services/                          # In-memory session management service
│   ├── launcher.py                        # Service orchestrator (env & CLI flags)
│   ├── main.py                            # ASGI entrypoint with request logging
│   ├── README.md                          # Backend architecture & API documentation
│   └── tests/                             # Backend unit and integration tests
│
├── frontend/                              # Accessible React 18 UI (Spoorthi V)
│   ├── src/
│   │   ├── components/                    # AppShell, VoiceControls, TranscriptTimeline
│   │   ├── hooks/                         # useVoiceRecorder custom Web Speech hook
│   │   ├── api_client.ts                  # Strictly-typed API client (zero 'any')
│   │   ├── App.tsx                        # Enterprise Studio workspace
│   │   └── styles.css                     # Responsive WCAG 2.1 AA styling
│   ├── src/__tests__/                     # Vitest component & hook test suite
│   ├── ACCESSIBILITY.md                   # Full WCAG 2.1 AA compliance audit report
│   ├── package.json                       # Frontend scripts & dependencies
│   ├── README.md                          # Frontend setup & architecture guide
│   └── vite.config.ts                     # Vite build & bundler configuration
│
├── packages/                              # Core Python Micro-Packages
│   │
│   ├── audio/                             # Audio Capture & VAD (Satwik A - Team Lead)
│   │   ├── mock_mic.py                    # 16-bit PCM streaming microphone simulator
│   │   ├── vad.py                         # Energy-based & simple Voice Activity Detectors
│   │   ├── cli.py                         # Real-time ASCII audio meter CLI demo
│   │   ├── models.py / schemas.py         # AudioConfig, AudioFrame, VADResult schemas
│   │   ├── types.ts                       # TypeScript audio definitions
│   │   ├── README.md                      # Audio pipeline documentation
│   │   └── tests/                         # Isolated audio unit & stress tests
│   │
│   ├── speech_to_text/                    # Speech-to-Text & Accumulator (Pavanchand RM)
│   │   ├── fake_transcriber.py            # Simulated STT & dynamic confidence scoring
│   │   ├── accumulator.py                 # Streaming chunk accumulator state machine
│   │   ├── cli.py                         # Live streaming transcription CLI demo
│   │   ├── models.py                      # TranscriptSegment & AccumulatedUtterance models
│   │   ├── types.ts                       # TypeScript speech interfaces
│   │   ├── README.md                      # STT architecture & pipeline documentation
│   │   └── tests/                         # STT unit, integration & memory tests
│   │
│   ├── context_reasoning/                 # Context & Reasoning (Praveen Kumar)
│   │   ├── context_manager.py             # Active window, screen & turn history manager
│   │   ├── prompt_manager.py              # Versioned prompt templates with variable injection
│   │   ├── mock_engine.py                 # Simulated reasoning & action-dispatch engine
│   │   ├── models.py                      # ContextState, ReasoningOutput data models
│   │   ├── types.ts                       # TypeScript context interfaces
│   │   ├── README.md                      # Context engine documentation
│   │   └── tests/                         # Context reasoning test suite
│   │
│   └── agentic_workflow/                 # Agentic Workflow & Tool Execution (Chiranthan RK)
│       ├── state_machine.py               # Multi-step decision FSM with safety gates (A–D)
│       ├── mock_executor.py               # Safe tool executor (file.search, file.move, calc)
│       ├── models.py                      # ActionPlan, WorkflowStep, ToolResult models
│       ├── types.ts                       # TypeScript workflow interfaces
│       ├── README.md                      # State machine transition & safety docs
│       └── tests/                         # Workflow unit & integration tests
│
├── docs/                                  # Team Specifications & Contracts
│   ├── architecture.md                    # Core architectural standards
│   ├── integration-contracts.md           # Inter-module data contract definitions
│   └── development-workflow.md            # Git branching rules & PR checklist
│
├── tests/                                 # End-to-End Test Suite
│   ├── integration/                       # Reserved for Week 4 cross-module pipelines
│   └── README.md                          # Testing philosophy & isolation strategy
│
├── pyproject.toml                         # Monorepo build & package discovery configuration
└── requirements.txt                       # Python dependencies (FastAPI, Pydantic, Pytest, Uvicorn)
```

---

## 👥 Team Members & Module Ownership

| Member | Responsibility | Package Path | Feature Branch |
| :--- | :--- | :--- | :--- |
| **Satwik A** *(Team Lead)* | Audio Capture & Voice Activity Detection | `packages/audio/` | `feature/audio-vad` |
| **Pavanchand RM** | Speech-to-Text & Segment Accumulator | `packages/speech_to_text/` | `feature/speech-to-text` |
| **Chiranthan RK** | Agentic Workflow & Mock Tool Execution | `packages/agentic_workflow/` | `feature/agentic-workflow` |
| **Apeksha KT** | Backend Gateway, Sessions & Launcher | `backend/` | `feature/backend-fastapi` |
| **Spoorthi V** | Frontend UI, AppShell & Virtualized Timeline | `frontend/` | `feature/frontend` |
| **Praveen Kumar** | Context Tracking & Versioned Reasoning | `packages/context_reasoning/` | `features/praveen-week1` |

---

## ⚡ Quickstart Guide

### 1. Prerequisites
- **Python**: Version 3.10+ (Recommended: Python 3.12)
- **Node.js**: Version 18+ (Recommended: Node 20 LTS)

### 2. Environment Setup

#### Clone the Repository:
```bash
git clone https://github.com/Tony-chopper1/SDK-9.git
cd SDK-9
```

#### Python Virtual Environment Setup:
```bash
# Create virtual environment:
python3 -m venv .venv

# Activate virtual environment:
source .venv/bin/activate       # On Linux / macOS
.venv\Scripts\activate          # On Windows (CMD)
.venv\Scripts\Activate.ps1      # On Windows (PowerShell)

# Install dependencies in editable mode:
pip install -r requirements.txt
pip install -e .
```

#### Frontend Dependencies:
```bash
cd frontend
npm ci
cd ..
```

---

## 🚀 Running the Services

### A. Start the Backend Gateway
```bash
# Using the dedicated service launcher:
python backend/launcher.py --port 8000 --reload

# Or directly with Uvicorn:
uvicorn backend.main:app --reload --port 8000
```
- **API Health**: `http://localhost:8000/api/v1/health`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

#### Core Backend Endpoints:
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check endpoint |
| POST | `/api/v1/sessions` | Create a new session |
| GET | `/api/v1/sessions` | Retrieve all active sessions |
| GET | `/api/v1/sessions/{session_id}` | Retrieve specific session details |
| POST | `/api/v1/sessions/{session_id}/pause` | Pause active session |
| POST | `/api/v1/sessions/{session_id}/stop` | Stop active session |

### B. Start the Frontend Studio
```bash
cd frontend
npm run dev
```
Open your browser at **`http://localhost:5173`** to access the voice studio interface.

### C. Run Standalone CLI Demos
Each micro-package provides an interactive terminal demonstration:

```bash
# Speech-to-Text & Streaming Accumulator Demo:
python -m packages.speech_to_text.cli

# Audio Capture & VAD Meter Demo:
python -m packages.audio.cli --iterations 10
```

---

## 🧪 Automated Testing Strategy

To ensure zero merge conflicts during parallel feature development, all unit tests are colocated within their respective module directories:

### Run Isolated Package Tests:
```bash
# Speech-to-Text:
pytest packages/speech_to_text/tests/ -v

# Audio & VAD:
pytest packages/audio/tests/ -v

# Agentic Workflow:
pytest packages/agentic_workflow/tests/ -v

# Backend Gateway:
pytest backend/tests/ -v

# Frontend Vitest Suite:
cd frontend && npm test -- --run
```

### Run Full Repository Test Suite:
```bash
pytest
```

---

## 🌿 Git & Branching Strategy

- **`main`**: Production-ready, stable milestone releases.
- **`develop`**: Central integration branch for all verified feature PRs.
- **`feature/*`**: Individual developer branches created from `develop`.

> [!IMPORTANT]
> Never push directly to `develop` or `main`. All contributions must be submitted via Pull Requests targeting `develop` after passing all local test suites.

---

## 📄 Shared Contracts & Documentation

Review the foundational specifications before implementing or modifying interfaces:
- `docs/architecture.md` - Core system architecture and data flows.
- `docs/integration-contracts.md` - Interservice JSON schemas, models, and TypeScript types.
- `docs/development-workflow.md` - Git branching policies, PR checklist, and code quality standards.

---

## 🔒 Security & Best Practices

- Never commit API keys, secrets, or personal credentials.
- Do not commit `.env` or temporary credential files (enforced by `.gitignore`).
- Do not upload real private audio recordings or confidential screen data.
- Utilize local mock providers and offline simulators during development.
