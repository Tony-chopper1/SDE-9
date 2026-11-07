# Audio & Voice Activity Detection (VAD) Module

**Owner**: Satwik A (`feature/audio-vad`)  
**Team**: SDE-9 / SDK-9 Voicebot  
**Module**: `packages/audio/`  

---

## 1. Overview & Architectural Role

The **Audio & VAD** module is the ingress foundation of the SDK-9 AI Voice Co-Pilot pipeline. It captures and streams discrete audio frames, performs Voice Activity Detection (VAD) to differentiate speech from background silence/noise, and provides deterministic offline simulation for cross-module development and automated testing.

### Key Capabilities
- **Typed Configurations & Frames**: Strongly validated audio parameters (sample rate, bit depth, channel count, frame duration) and immutable frame models.
- **Deterministic Mock Microphone**: Hardware-free, offline audio synthesizer that generates repeatable 16-bit PCM waveforms for speech, silence, alternating cycles, and custom timelines.
- **Provider-Neutral VAD Interface**: Pluggable `BaseVAD` abstract contract supporting scripted/mock detectors and real-time energy-based detectors.
- **Energy-Based VAD**: Zero-dependency RMS energy detector with hangover smoothing and trigger confirmation to avoid word clipping.
- **Contract & Envelope Compliance**: Adheres to the SDK-9 event envelope and error envelope specifications in `docs/integration-contracts.md`.
- **Interactive CLI Demo**: Terminal utility featuring a live ASCII audio level meter and speech detection indicators.

---

## 2. Implementation Language & Architectural Rationale

* **Language**: Python ($\ge 3.10$)
* **Location**: `packages/audio/` (configured on `pythonpath` in `pyproject.toml`)
* **Rationale**:
  1. The SDK-9 repository is structured as a unified Python monorepo (`pyproject.toml`, `requirements.txt`).
  2. Sibling consumer modules—specifically Speech-to-Text (`packages/speech_to_text/`) and the FastAPI backend (`backend/`)—are written in Python. Python schemas enable direct, zero-overhead in-process imports (`from audio.schemas import AudioFrame`).
  3. The automated test harness across the repository is `pytest`.
  4. The schemas provide Pydantic v2-compatible methods (`model_dump()`, `model_validate()`) while running with zero external dependencies to ensure full portability across development environments.
  5. *TypeScript Support*: `packages/audio/types.ts` provides strongly typed TypeScript definitions corresponding 1:1 with Python Pydantic models in `models.py`.

---

## 2.1 Python & TypeScript Schema Correspondence

The TypeScript definitions in `packages/audio/types.ts` mirror the Python Pydantic models in `packages/audio/models.py`:

| Python Model (`models.py`) | TypeScript Definition (`types.ts`) | Data / Wire Type Mapping | Field Semantics & Contract Notes |
| :--- | :--- | :--- | :--- |
| `VADState(str, Enum)` | `const VADState = { ... } as const`<br>`type VADState` | `string` union: `'SILENCE' \| 'SPEECH_START' \| 'SPEECH' \| 'SPEECH_END'` | Identical enum values for tracking speech/silence transition states. |
| `AudioConfig(BaseModel)` | `interface AudioConfig` | `sample_rate: number`<br>`bit_depth: number`<br>`channels: number`<br>`format: string`<br>`frame_duration_ms: number` | Stream configuration. Defaults: 16 kHz, 16-bit PCM, mono. `frame_duration_ms=30` is approved team baseline; `20` is provisional STT. |
| `AudioFrame(BaseModel)` | `interface AudioFrame` | `data`: `Uint8Array \| ArrayBuffer \| string`<br>`timestamp`: `number` (epoch sec)<br>`sample_rate`: `number`<br>`frame_index`: `number`<br>`is_speech`: `boolean`<br>`timestamp_ms`: `number` (stream ms)<br>`timestamp_utc`: `string` (ISO 8601) | Discrete audio frame. Python `bytes` corresponds to `Uint8Array` in JS/TS or `base64` string in JSON serialization. |
| `VADResult(BaseModel)` | `interface VADResult` | `is_speech: boolean`<br>`confidence: number`<br>`energy_db: number`<br>`metadata?: Record<string, unknown>` | Frame classification result with confidence score in `[0.0, 1.0]` and dBFS level. |
| `VADEvent(BaseModel)` | `interface VADEvent` | `state: VADState`<br>`timestamp: number`<br>`energy_level: number`<br>`confidence: number`<br>`frame_index?: number`<br>`timestamp_ms?: number` | Internal VAD detection event tracking state transitions (`SILENCE`, `SPEECH_START`, `SPEECH`, `SPEECH_END`). |
| `EventEnvelope(BaseModel)` | `interface EventEnvelope<T>` | `event_id: string`<br>`event_type: string`<br>`schema_version: string`<br>`session_id: string`<br>`correlation_id: string`<br>`timestamp: string`<br>`producer: string`<br>`payload: T` | Shared SDK-9 event envelope conforming to `docs/integration-contracts.md`. Produced via `vadEvent.to_envelope()`. |

### Timestamp Semantics in Both Languages
- **`timestamp`** (`float` in Python / `number` in TypeScript): Unix epoch wall-clock timestamp in fractional seconds (e.g. `1730304000.123`).
- **`timestamp_ms`** (`float` in Python / `number` in TypeScript): Audio-relative stream offset in milliseconds advancing monotonically from `0.0` (e.g. `0.0, 20.0, 40.0`).
- **`timestamp_utc`** (`str` in Python / `string` in TypeScript): Wall-clock UTC timestamp in ISO 8601 format (e.g. `'2026-10-30T14:30:00.000000+00:00'`).

### Approved Team Defaults vs. Provisional STT Contract
- **Approved Team Baseline**: 16,000 Hz, 16-bit PCM (`s16le`), Mono (1 channel), **30 ms** frame duration (**960 bytes** per frame).
- **Provisional STT Contract**: **20 ms** frame duration (**640 bytes** per frame), with provisional fields `audio_data`, `sequence_number`, and `timestamp_ms` supported for downstream transcription compatibility. Marked as provisional pending Week 2 joint testing.

---

## 3. Audio & Frame Contract (Provisional STT Interface)

> [!NOTE]
> **Provisional Status**: The audio interface below was proposed by the Speech-to-Text developer (Pavan) and implemented in `packages/audio/`. It is currently documented as **provisional** pending joint integration testing and team-lead review.

### Contract Parameters
- **Sample Rate**: 16,000 Hz (`16 kHz`)
- **Channels**: 1 (Mono)
- **Sample Format**: Signed 16-bit little-endian PCM (`s16le`)
- **Internal Payload**: Raw Python `bytes` (`audio_data`)
- **Default Frame Duration**: 20 ms
- **Supported Frame Durations**: 20 ms and 30 ms

### Expected Payload Sizes
- **20 ms Frame**: **640 bytes** ($16000 \times 0.020 \times 1 \times 2$)
- **30 ms Frame**: **960 bytes** ($16000 \times 0.030 \times 1 \times 2$)

### Frame Data Structure (`AudioFrame`)
Every frame produced by the audio module exposes the agreed fields:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `audio_data` | `bytes` | Raw 16-bit PCM byte payload (`s16le`). |
| `sample_rate` | `int` | Sampling frequency in Hz (default: `16000`). |
| `channels` | `int` | Number of channels (default: `1` for mono). |
| `format` | `str` | Audio encoding format (default: `"s16le"`). |
| `frame_duration_ms` | `int` | Duration of discrete frame in ms (`20` or `30`). |
| `sequence_number` | `int` | Zero-based, monotonically increasing index preserving temporal order. |
| `timestamp_ms` | `float` | Audio-relative timeline position advancing by frame duration (e.g. `0.0, 20.0, 40.0`). |
| `frame_id` | `str` | Unique frame identifier string (e.g. `frame-a1b2c3d4e5`). |
| `timestamp_utc` | `str` | ISO 8601 wall-clock UTC timestamp for logging/auditability. |

---

## 4. End-of-Stream (EOS) Specification

To ensure clear stream termination across module boundaries:

1. **EOF Return Value**:
   - `AudioSource.read_frame()` returns `None` when the stream concludes or when maximum duration is reached.
2. **Clean Generator Termination**:
   - `AudioSource.stream()` cleanly raises `StopIteration` without emitting extra frames.
3. **Empty Frames Prohibited**:
   - Empty audio frames (`audio_data=b""` or truncated byte length) are **strictly rejected** during `AudioFrame` validation with an `AudioFrameValidationError`.
   - An empty frame is never used as an EOF sentinel.

---

## 5. Schemas & Envelopes

### `AudioConfig`
```python
from audio.schemas import AudioConfig

config = AudioConfig(
    sample_rate=16000,
    channels=1,
    bit_depth=16,
    format="s16le",
    frame_duration_ms=20,
)
print(config.frame_size_bytes)  # 640 bytes
```

### `AudioFrame`
```python
from audio.schemas import AudioFrame

frame = AudioFrame(
    audio_data=raw_pcm_bytes,  # 640 bytes
    sequence_number=0,
    timestamp_ms=0.0,
    sample_rate=16000,
    channels=1,
    format="s16le",
    frame_duration_ms=20,
)
rms = frame.calculate_rms()    # RMS amplitude
dbfs = frame.calculate_dbfs()  # Decibels relative to full scale
```

### `VADEvent` (SDK-9 Event Envelope)
Conforms to `docs/integration-contracts.md`:
```json
{
  "event_id": "evt-7c9403f98e44",
  "event_type": "audio.vad.speech_start",
  "schema_version": "1.0.0",
  "session_id": "session-001",
  "correlation_id": "corr-001",
  "timestamp": "2026-10-30T00:00:00.000000+00:00",
  "producer": "packages.audio",
  "payload": {
    "frame_id": "frame-001",
    "sequence_number": 0,
    "timestamp_ms": 0.0,
    "energy_db": -11.8
  }
}
```

### Error Envelope
When validation or processing fails, typed exceptions (`AudioConfigError`, `AudioFrameValidationError`, `AudioSourceError`, `VADError`) provide sanitized error envelopes:
```json
{
  "code": "AUDIO_CONFIG_INVALID",
  "message_safe_for_user": "Unsupported sample rate: 12345. Supported rates: [8000, 16000, 22050, 24000, 32000, 44100, 48000]",
  "retryable": false,
  "correlation_id": null,
  "details_redacted": { "sample_rate": 12345 }
}
```

---

## 6. Mock Microphone Source

The `MockMicSource` operates entirely offline without physical sound cards or binary drivers.

```python
from audio.source import MockMicSource

# Continuous speech synthesis
with MockMicSource(pattern="speech", duration_seconds=1.0) as mic:
    for frame in mic.stream():
        process(frame)

# Alternating speech (600ms) and silence (600ms) cycles
with MockMicSource(pattern="alternating", max_frames=50) as mic:
    for frame in mic.stream():
        process(frame)

# Custom timeline sequence
timeline = [("silence", 200), ("speech", 500), ("silence", 300)]
with MockMicSource(pattern="custom", custom_timeline=timeline) as mic:
    for frame in mic.stream():
        process(frame)
```

---

## 7. Voice Activity Detection (VAD)

### Abstract Interface (`BaseVAD`)
```python
from audio.vad import BaseVAD

class BaseVAD(ABC):
    @abstractmethod
    def process_frame(self, frame: AudioFrame) -> VADResult: ...

    @abstractmethod
    def reset(self) -> None: ...
```

### Implementations
1. **`MockVAD`**: Fully deterministic for unit tests. Can replay pre-scripted boolean decisions (`[True, False, True]`) or use simple thresholding.
2. **`EnergyVAD`**: Lightweight RMS energy detector. Includes:
   - `threshold_db` (default: `-42.0` dBFS)
   - `hangover_frames` (default: `3` frames; preserves active state across intra-word pauses)
   - `trigger_frames` (default: `2` frames; filters impulsive clicks)

---

## 8. CLI Demonstration Tool

The module includes an interactive terminal tool demonstrating audio capture and VAD classification:

```bash
# Run alternating speech/silence demo (2.0 seconds)
python packages/audio/cli.py --pattern alternating --duration 2.0

# Run in pure silence or continuous speech
python packages/audio/cli.py --pattern silence --duration 1.0
python packages/audio/cli.py --pattern speech --duration 1.0

# Run with 30ms frames (960 bytes)
python packages/audio/cli.py --pattern alternating --frame-ms 30 --duration 1.5

# Simulate real-time microphone pacing
python packages/audio/cli.py --pattern alternating --duration 3.0 --realtime

# Use scripted Mock VAD instead of Energy VAD
python packages/audio/cli.py --vad-engine mock --duration 1.5
```

### Sample Output
```text
====================================================================
  SDK-9 AI Voice Co-Pilot — Audio & VAD Module Demonstration
====================================================================
  Configuration : 16000 Hz, 16-bit PCM, Mono, 20ms frames
  Mock Source   : pattern='alternating', duration=0.6s, real_time=False
  VAD Engine    : ENERGY (threshold: -42.0 dBFS)
--------------------------------------------------------------------
  SEQ   TIME_MS   UTC_TIME        RMS     dBFS    METER                 STATE
---------------------------------------------------------------------------
  0000       0ms  19:04:33.294     8418.3   -11.8  [==============    ]   [SILENCE]
  0001      20ms  19:04:33.295     9109.1   -11.1  [===============   ]   [SPEECH] 
  0002      40ms  19:04:33.295     9372.6   -10.9  [===============   ]   [SPEECH] 
...
--------------------------------------------------------------------
Pipeline Summary:
  Total frames processed : 30
  Speech frames detected : 29 (96.7%)
  Wall-clock time        : 0.01s
  Sample Event Envelope  : ID=evt-7c9403f98e44, Version=1.0.0
====================================================================
Demo completed successfully.
```

---

## 9. Test Execution & Coverage

Tests are executed with `pytest`:

```bash
# Run all unit and integration tests
pytest

# Run tests with coverage report
pytest --cov=packages/audio --cov-report=term-missing
```

### Test Coverage Results
- **Total Tests**: 30 passed
- **Coverage**: **92%** (exceeds the >80% task requirement)
- **Test Modules**:
  - `tests/unit/test_audio_schemas.py`: Configuration validation, frame sizing math (640B and 960B), rejection of empty frames as EOS, error envelopes, serialization.
  - `tests/unit/test_mock_mic.py`: Deterministic byte reproduction, stream generators, pattern switching, explicit EOF return (None).
  - `tests/unit/test_vad.py`: MockVAD scripting, EnergyVAD speech/silence separation, hangover smoothing.
  - `tests/unit/test_audio_cli.py`: Meter rendering, fast execution, error exit handling, main entrypoint.
  - `tests/integration/test_audio_pipeline.py`: Full end-to-end stream $\rightarrow$ VAD $\rightarrow$ Event envelope pipeline for 20ms and 30ms frames.

---

## 10. Summary of Assumptions & Provisional Contract Status

1. **Provisional STT Contract**: The fields (`audio_data`, `sample_rate`, `channels`, `format`, `frame_duration_ms`, `sequence_number`, `timestamp_ms`) are implemented in `AudioFrame` and remain internal to `packages/audio/` until approved in review.
2. **End-of-Stream Delivery**: `AudioSource.read_frame()` returns `None` to indicate EOF. Sibling modules receiving frames over streams or queues should check for `None` or listen to `audio.stream.end` events rather than expecting empty byte payloads.
3. **No Cross-Module Contamination**: No files outside `packages/audio/` and `tests/` were created or modified.
