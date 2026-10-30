# Automated Testing Strategy (SDK-9)

## Weeks 1–3: Colocated Unit & Component Tests
To maintain complete developer independence and prevent Git merge conflicts, all unit and module tests are placed directly inside each module's folder:

- Audio & VAD: `packages/audio/tests/`
- Speech-to-Text: `packages/speech_to_text/tests/`
- Context & Reasoning: `packages/context_reasoning/tests/`
- Agentic Workflow: `packages/agentic_workflow/tests/`
- Backend API: `backend/tests/`
- Frontend UI: `frontend/tests/`

### Running Individual Module Tests:
```bash
# Satwik:
pytest packages/audio/tests

# Pavanchand:
pytest packages/speech_to_text/tests

# Praveen:
pytest packages/context_reasoning/tests

# Chiranthan:
pytest packages/agentic_workflow/tests

# Apeksha:
pytest backend/tests
```

### Running the Entire Test Suite (All Modules):
```bash
pytest
```

---

## Week 4: End-to-End (E2E) Integration Tests
The `tests/integration/` directory is reserved for Week 4 cross-module pipelines (e.g., streaming audio frames through STT, context engine, agent state machine, and FastAPI gateway).
