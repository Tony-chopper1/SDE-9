SDK-9 Integration Contracts

Purpose:

This document defines the initial shared contracts between SDK-9 modules. Members must discuss and agree on contract changes before implementing incompatible changes.


Event Envelope:

Events exchanged between modules should use a consistent envelope containing:

- "event_id"
- "event_type"
- "schema_version"
- "session_id"
- "correlation_id"
- "timestamp"
- "producer"
- "payload"

The payload contains the data specific to the event type.

Timestamps must use UTC ISO 8601 format.

Speech-to-Text Contracts

The Speech-to-Text module must provide the following components.

TranscriptSegment

Represents one segment of recognized speech. The team must agree on its exact fields and types before implementation.

TranscriptEvent

Represents a transcript-related event that can be consumed by other modules.

Provider-Neutral Adapter

Provides a common interface so the application can use either a real provider or a deterministic fake transcriber.

Ordered Segment Accumulator

Combines transcript segments while preserving their intended order.

Shared Data Structure Rules

Before implementation and integration, the team must agree on:

- Field names and data types.
- Required and optional fields.
- Timestamp conventions.
- Input validation rules.
- Expected behavior for invalid or missing data.


Error Envelope:

Errors crossing module boundaries should expose:

- "code"
- "message_safe_for_user"
- "retryable"
- "correlation_id"
- "details_redacted"

Do not include secrets or sensitive payloads in errors.


Session States:

Use these agreed state names for sessions:

- "created"
- "active"
- "paused"
- "stopping"
- "completed"
- "failed"
- "expired"


Workflow States:

Use these agreed state names for workflows:

- "draft"
- "awaiting_approval"
- "running"
- "paused"
- "succeeded"
- "failed"
- "cancelled"


Contract Rules:

- Use typed input and output structures.
- Version schemas when their structure changes incompatibly.
- Incompatible schema changes require a version update and team review.
- Document required and optional fields for each shared data structure.
- Reject invalid payloads with clear, safe errors.
- Avoid circular imports between modules.
- Keep mock implementations available for local development and automated tests.
- Discuss shared contract changes with the team before merging them.
- Keep all modules compatible with the agreed contracts.