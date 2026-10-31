SDK-9 Architecture

Project Overview:

SDK-9 is an independent team implementation of the AcademiaAI AI Voicebot. The application must be runnable in mock mode without paid API credentials.


High-Level Components:

1. Audio

- Defines audio data structures and audio errors.
- Provides audio chunking and Voice Activity Detection (VAD).

2. Speech-to-Text

- Defines transcript data structures.
- Converts audio input into transcript segments through a provider-neutral interface.
- Provides a deterministic fake transcriber for development and testing.
- Maintains transcript segment ordering.

3. Context and Reasoning

- Defines context items, source references, and reasoning request/result structures.
- Builds context and produces structured reasoning results.
- Uses mock implementations during development.

4. Agentic Workflow

- Defines workflow plans, steps, tools, approval requests, and results.
- Executes permitted mock tools through a controlled workflow.
- Supports approval gates and workflow states.

5. Backend

- Uses Python and FastAPI.
- Exposes application APIs and manages session lifecycle.
- Provides health checks and safe error responses.

6. Frontend

- Uses React and TypeScript.
- Displays session controls, transcript events, and workflow progress.
- Supports mock-mode interaction.


Integration Principles:

- Each module must expose a clear, documented interface.
- Shared data structures must be agreed upon before integration.
- Use mock implementations so modules can be developed independently.
- Keep domain logic, API routes, and tests separated.
- Run automated tests before merging changes into "develop".


Privacy and Safety:

- Mock mode is enabled by default.
- Screen context capture must be opt-in.
- Never commit API keys, real recordings, private screen captures, or personal data.