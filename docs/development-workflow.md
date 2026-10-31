SDK-9 Development Workflow

Branch Strategy:

- "main": Stable, tested releases only.
- "develop": Team integration branch.
- Each member works on an individual feature branch created from "develop".

Feature Branches:

- "feature/audio-vad"
- "feature/speech-to-text"
- "feature/context-reasoning"
- "feature/agentic-workflow"
- "feature/backend-fastapi"
- "feature/frontend"

Daily Git Workflow:

1. Switch to your feature branch.
2. Pull the latest changes from "develop" before starting new work.
3. Implement a small, focused change.
4. Run relevant tests and review the changes.
5. Commit meaningful checkpoints locally.
6. Push commits to your feature branch regularly.
7. Open or update a pull request targeting "develop" when ready for review.

Safety Rules:

- Never push directly to "main".
- Do not force-push shared branches.
- Review "git status" and "git diff" before committing.
- Never commit ".env" files, API keys, recordings, screen captures, or personal data.
- Keep mock mode working without paid API credentials.
- Coordinate changes to shared interfaces with the team.

Pull Request Requirements:

- Explain what changed and why.
- Include relevant test results.
- Request a review from a teammate.
- Merge only after review and required checks pass.