# Speech-to-Text Provider Setup Guide & Known Limitations

> **SDK-9 AI Voice Co-Pilot — Day 28–30 Release Gate Deliverable**  
> **Module**: `packages/speech_to_text/`  
> **Default Mode**: Offline Mock Provider (`FakeTranscriberService`)

---

## 1. Provider Configuration & Environment Variables

The SDK-9 Speech-to-Text module uses a provider-neutral adapter architecture. It operates in **offline mock mode by default** requiring **zero paid cloud credentials, zero external API keys, and zero hardware audio dependencies**.

### Configuration Matrix

| Variable | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `STT_PROVIDER` | `string` | `"mock"` | Active speech recognition provider: `"mock"`, `"google_cloud"`, or `"whisper"`. |
| `STT_MOCK_MODE` | `boolean` | `true` | When `true`, enforces deterministic simulated speech recognition locally. |
| `STT_CONFIDENCE_THRESHOLD` | `float` | `0.65` | Boundary threshold `[0.0, 1.0]`. Segments scoring below are flagged/handled. |
| `STT_LOW_CONFIDENCE_ACTION`| `string` | `"tag"` | Strategy for low-confidence chunks: `"tag"` (mark `is_low_confidence=True`) or `"filter"` (suppress from output). |
| `STT_ENABLE_FALLBACK` | `boolean` | `true` | When `true`, automatically falls back to `FakeTranscriberService` on quota or network failure. |
| `STT_ENABLE_REVISION_EVENTS`| `boolean`| `true` | When `true`, emits `transcript.revised` events when interim drafts are updated. |
| `GOOGLE_APPLICATION_CREDENTIALS` | `path` | `""` | Absolute path to Google Cloud service account JSON (only required if `STT_PROVIDER="google_cloud"`). **Never commit credentials.** |

---

## 2. Mock Provider vs. Real Cloud Provider

### Mock Provider (`FakeTranscriberService`) — *Default*
- **Operational Requirements**: Pure Python 3.12+ and Pydantic. No network connection or API keys required.
- **Determinism**: Generates reproducible transcripts with fixed base timestamps (`0.0`), calibrated dynamic confidence scores, and standardized voice co-pilot dialogue scenarios.
- **Use Cases**: Local development, CI test pipelines, latency benchmarking, and release gate demonstration.

### Real Cloud Provider (Google Cloud Speech-to-Text / Whisper)
- **Operational Requirements**: Valid GCP project with Cloud Speech-to-Text API enabled, or local Whisper PyTorch runtime.
- **Fail-Safe Mechanism**: The `SpeechToTextOrchestrator` implements an automatic fallback circuit. If a real provider encounters:
  - **Quota Exhaustion** (`HTTP 429`, `ResourceExhausted`), or
  - **Network Disconnects** (`ConnectionResetError`, `TimeoutError`)
  
  The engine normalizes the exception into a typed `STTError` envelope, dispatches a `transcript.fallback` event, and continues transcription via `FakeTranscriberService` without dropping audio or failing the session.

---

## 3. Known Limitations

1. **Acoustic Audio Codec**:
   - The engine operates exclusively on **16-bit linear PCM (s16le)**. Compressed audio containers (`.mp3`, `.ogg`, `.opus`, `.aac`, `.webm`) must be decoded to raw PCM by the frontend (using Web Audio API) or an upstream media service before being ingested.
2. **Resampling Compute Budget**:
   - Audio sampled at non-standard rates (e.g. 44.1 kHz, 48 kHz, stereo) is automatically resampled and normalized to 16 kHz mono. This adds an average latency of ~0.16 ms per 20 ms frame. While well within real-time budgets (< 5 ms), very low-power embedded microcontrollers should stream native 16 kHz where possible.
3. **Multilingual Mid-Stream Code-Switching**:
   - The mock provider defaults to English (`"en"`). Dynamic detection of mid-sentence spoken language switching requires external real provider capabilities.
4. **Permanent Network Isolation**:
   - If a real cloud provider suffers permanent network isolation with fallback disabled (`STT_ENABLE_FALLBACK=false`), the orchestrator transitions to `ERROR` state and halts until restarted. Always retain `STT_ENABLE_FALLBACK=true` in production deployments.

---

## 4. Clean-Clone Setup & Verification Guide

Follow these steps on a clean machine to run and verify the STT module:

```bash
# 1. Clone repository
git clone https://github.com/Tony-chopper1/SDK-9.git
cd SDK-9

# 2. Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the Full STT Test Suite (all passing offline)
pytest packages/speech_to_text/tests/ -v

# 5. Run the Reproducible Latency Benchmark
python -m packages.speech_to_text.benchmark --iterations 200

# 6. Run the Interactive Release Demo
python packages/speech_to_text/cli.py
```
