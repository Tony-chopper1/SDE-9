# Speech-to-Text & Segment Accumulator Module

**Owner:** Pavanchand R M (Team Lead)  
**Task ID:** W2  
**Branch:** `feature/speech-to-text`

---

## 1. Overview
The `speech_to_text` package handles the conversion of incoming audio streams into structured, chronologically ordered text transcript segments. It provides deterministic mock transcription for offline testing and an accumulator state machine to aggregate streaming chunks into complete user utterances.

---

## 2. Components

### `models.py`
Defines canonical Pydantic models for speech processing:
- **`TranscriptSegment`**: Atomic transcript chunk with timing, confidence (`0.0`–`1.0`), and interim vs final status (`is_final`).
- **`AccumulatorState`**: State enum (`IDLE`, `ACCUMULATING`, `PAUSED`, `FINALIZED`).
- **`AccumulatedUtterance`**: The synthesized sentence or command containing merged segments and computed duration.
- **`TranscriptEvent`**: Event wrapper for internal pipeline messaging.

### `fake_transcriber.py`
Provides deterministic simulated transcription mapping to the official PRD use cases:
- `transcribe(audio_data, phrase_index, start_time_offset)`: Single-shot transcription with realistic timing.
- `simulate_streaming_chunks(phrase_index, start_time_offset)`: Emits word-by-word streaming partials (`is_final=False`) followed by a final segment (`is_final=True`).

### `accumulator.py`
State machine for streaming transcription aggregation:
- **Chronological Sorting**: Automatically handles out-of-order chunk arrivals.
- **Interim Overwrite**: Deduplicates and overwrites interim segments when a final version with the same ID arrives.
- **Memory Leak Protection**: Completely purges internal buffers upon `finalize_utterance()` to ensure zero memory accumulation over long sessions.

---

## 3. Running Unit Tests & Coverage
Run isolated tests for this module:
```bash
pytest packages/speech_to_text/tests/ -v
```

Run test coverage report:
```bash
pytest --cov=packages/speech_to_text packages/speech_to_text/tests/
```
*Current test suite: 15 passing tests, **99% code coverage**.*

---

## 4. Acceptance Criteria Verification
- [x] Transcript schemas validate without errors.
- [x] Fake transcriber produces valid segments and streaming chunks.
- [x] Accumulator handles overlapping timestamps and out-of-order chunks.
- [x] Test coverage >80% (Achieved: **99%**).
- [x] No memory leaks on large transcript sets (Stress-tested with 1,000+ segments).
- [x] Documentation complete.
