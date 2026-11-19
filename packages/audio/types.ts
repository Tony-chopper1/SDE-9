/**
 * TypeScript type definitions for the SDK-9 Audio & VAD module.
 * Owner: Satwik A (feature/audio-vad)
 *
 * Corresponds to Python models in:
 * - packages/audio/models.py
 * - packages/audio/schemas.py
 *
 * Conforms to:
 * - docs/architecture.md
 * - docs/integration-contracts.md (SDK-9 Event Envelope & Error Envelope)
 * - Provisional Speech-to-Text (STT) audio contract
 */

// ============================================================================
// Supported Audio Parameter Constants
// ============================================================================

export const SUPPORTED_SAMPLE_RATES = [8000, 16000, 22050, 24000, 32000, 44100, 48000] as const;
export type SupportedSampleRate = (typeof SUPPORTED_SAMPLE_RATES)[number];

export const SUPPORTED_BIT_DEPTHS = [16] as const;
export type SupportedBitDepth = (typeof SUPPORTED_BIT_DEPTHS)[number];

export const SUPPORTED_CHANNELS = [1, 2] as const;
export type SupportedChannels = (typeof SUPPORTED_CHANNELS)[number];

export const SUPPORTED_FRAME_DURATIONS_MS = [10, 20, 30] as const;
export type SupportedFrameDurationMs = (typeof SUPPORTED_FRAME_DURATIONS_MS)[number];

export const SUPPORTED_FORMATS = ['s16le'] as const;
export type SupportedFormat = (typeof SUPPORTED_FORMATS)[number];

// ============================================================================
// Contract Status Definitions
// ============================================================================

/**
 * Approved Team Baseline Settings:
 * Standard team baseline agreed for Week 1 starter templates.
 */
export const APPROVED_TEAM_DEFAULTS = {
  sample_rate: 16000,
  bit_depth: 16,
  channels: 1,
  format: 's16le',
  frame_duration_ms: 30, // 30ms = 960 bytes per frame (480 samples * 1 ch * 2 bytes)
  status: 'APPROVED',
} as const;

/**
 * Provisional Speech-to-Text (STT) Settings:
 * Proposed by STT developer (Pavan) for downstream streaming transcription.
 * NOTE: Provisional pending joint integration testing in Week 2.
 */
export const PROVISIONAL_STT_SETTINGS = {
  sample_rate: 16000,
  bit_depth: 16,
  channels: 1,
  format: 's16le',
  frame_duration_ms: 20, // 20ms = 640 bytes per frame (320 samples * 1 ch * 2 bytes)
  status: 'PROVISIONAL',
} as const;

// ============================================================================
// VAD State Enum
// ============================================================================

/**
 * Voice Activity Detection states matching Python packages.audio.models.VADState.
 * Defined as a const object and union type for complete compatibility across
 * all TypeScript compilers and runtime type-stripping runtimes.
 */
export const VADState = {
  SILENCE: 'SILENCE',
  SPEECH_START: 'SPEECH_START',
  SPEECH: 'SPEECH',
  SPEECH_END: 'SPEECH_END',
} as const;

export type VADState = (typeof VADState)[keyof typeof VADState];
export type VADStateString = VADState;

// ============================================================================
// Audio Format & Configuration Schemas
// ============================================================================

/**
 * Format specification schema for audio capture and streaming.
 * Matches Python packages.audio.models.AudioFormat.
 */
export interface AudioFormat {
  /** Sampling frequency in Hz (default: 16000). Supported: 8000..48000 */
  sample_rate: number;

  /** Bit depth per sample (default: 16). Supported: 16 */
  bit_depth: number;

  /** Audio channels: 1 = mono, 2 = stereo (default: 1) */
  channels: number;

  /** Audio encoding format (default: 's16le' - signed 16-bit little-endian PCM) */
  format: string;
}

/**
 * Configuration schema for audio capture and streaming.
 * Extends AudioFormat with discrete frame duration settings.
 * Matches Python packages.audio.models.AudioConfig.
 */
export interface AudioConfig extends AudioFormat {
  /**
   * Discrete frame duration in milliseconds.
   * - 30ms (default): Approved team baseline (960 bytes at 16kHz mono).
   * - 20ms: Provisional STT interface setting (640 bytes at 16kHz mono).
   */
  frame_duration_ms: number;
}

// ============================================================================
// Audio Frame & Chunk Schemas
// ============================================================================

/**
 * Discrete audio frame produced by the audio module.
 * Matches Python packages.audio.models.AudioFrame.
 *
 * Timestamp Semantics:
 * - timestamp: Unix epoch wall-clock timestamp in fractional seconds (e.g. 1730304000.123).
 * - timestamp_ms: Audio-relative timeline position advancing from 0.0 in milliseconds (e.g. 0.0, 20.0, 40.0).
 * - timestamp_utc: ISO 8601 wall-clock UTC string (e.g. '2026-10-30T14:30:00.000000+00:00').
 *
 * Payload Format:
 * - data / audio_data: Raw signed 16-bit little-endian PCM bytes (Uint8Array / ArrayBuffer in TS, or base64 string for JSON wire transfer).
 */
export interface AudioFrame {
  // Team starter interface fields
  /** Raw 16-bit PCM byte payload (s16le). In JS/TS represented as Uint8Array, ArrayBuffer, or base64 string. */
  data: Uint8Array | ArrayBuffer | string;

  /** Unix epoch wall-clock timestamp in fractional seconds (e.g. 1730304000.123). */
  timestamp: number;

  /** Sampling frequency in Hz (default: 16000). */
  sample_rate: number;

  /** Zero-based monotonic frame index. */
  frame_index: number;

  /** Speech classification flag. */
  is_speech: boolean;

  // Provisional STT interface & metadata fields
  /** Provisional STT payload alias matching data. */
  audio_data?: Uint8Array | ArrayBuffer | string;

  /** Audio channel count (default: 1 for mono). */
  channels?: number;

  /** Audio sample encoding format (default: 's16le'). */
  format?: string;

  /** Frame duration in ms (30ms team default; 20ms provisional STT). */
  frame_duration_ms?: number;

  /** Monotonically increasing sequence number preserving stream ordering. */
  sequence_number?: number;

  /** Audio-relative stream offset advancing in milliseconds from stream start (0.0, 20.0, 40.0, ...). */
  timestamp_ms?: number;

  /** Unique frame identifier string (e.g. 'frame-a1b2c3d4e5'). */
  frame_id?: string;

  /** ISO 8601 UTC wall-clock timestamp string for logging/auditability. */
  timestamp_utc?: string;
}

/**
 * Discrete audio chunk produced by the audio module.
 * Extends AudioFrame, providing chunk-specific aliases.
 * Matches Python packages.audio.models.AudioChunk.
 */
export interface AudioChunk extends AudioFrame {
  /** Identifier for this audio chunk (alias for frame_id). */
  chunk_id?: string;
  /** Monotonic chunk index (alias for frame_index). */
  chunk_index?: number;
}

// ============================================================================
// VAD Result Schema
// ============================================================================

/**
 * Voice Activity Detection classification result for an individual audio frame.
 * Matches Python packages.audio.models.VADResult.
 */
export interface VADResult {
  /** True if speech is detected; False for silence. */
  is_speech: boolean;

  /** Confidence score between 0.0 and 1.0 (default: 0.95). */
  confidence: number;

  /** Measured frame energy in dB relative to full scale (dBFS; -100.0 to 0.0). */
  energy_db: number;

  /** Diagnostic engine metadata (e.g. engine name, hangover state, consecutive counts). */
  metadata?: Record<string, unknown>;
}

// ============================================================================
// Internal VAD Event Schema
// ============================================================================

/**
 * Internal VAD event representing state transitions or frame classifications.
 * Matches Python packages.audio.models.VADEvent.
 */
export interface VADEvent {
  /** Current VAD transition state (SILENCE, SPEECH_START, SPEECH, SPEECH_END). */
  state: VADState;

  /** Unix epoch wall-clock timestamp in fractional seconds. */
  timestamp: number;

  /** Calculated frame energy level (linear RMS amplitude or dBFS level). */
  energy_level: number;

  /** Classification confidence score [0.0, 1.0] (default: 0.95). */
  confidence: number;

  /** Associated audio frame index (default: 0). */
  frame_index?: number;

  /** Audio-relative stream offset in milliseconds. */
  timestamp_ms?: number;
}

// ============================================================================
// Shared SDK-9 Event Envelope Schema
// ============================================================================

/**
 * Standard SDK-9 Event Envelope strictly conforming to docs/integration-contracts.md.
 * Matches Python packages.audio.models.EventEnvelope.
 */
export interface EventEnvelope<T = Record<string, unknown>> {
  /** Unique event UUID string (e.g. 'evt-7c9403f98e44'). */
  event_id: string;

  /** Dot-notated event name (e.g. 'audio.vad.speech_start', 'audio.vad.summary'). */
  event_type: string;

  /** Semantic schema version string (default: '1.0.0'). */
  schema_version: string;

  /** Unique session identifier string. */
  session_id: string;

  /** Tracing correlation identifier string across module boundaries. */
  correlation_id: string;

  /** Wall-clock timestamp in UTC ISO 8601 format (e.g. '2026-10-30T14:30:00.000Z'). */
  timestamp: string;

  /** Originating module identifier (default: 'packages.audio'). */
  producer: string;

  /** Event-specific payload dictionary. */
  payload: T;
}

// ============================================================================
// Type Guards
// ============================================================================

/**
 * Type guard verifying whether a value is a valid VADState enum value.
 */
export function isVADState(value: unknown): value is VADState {
  return (
    typeof value === 'string' &&
    Object.values(VADState).includes(value as VADState)
  );
}

/**
 * Type guard verifying whether an object conforms to AudioConfig.
 */
export function isAudioConfig(obj: unknown): obj is AudioConfig {
  if (!obj || typeof obj !== 'object') return false;
  const c = obj as Record<string, unknown>;
  return (
    typeof c.sample_rate === 'number' &&
    typeof c.bit_depth === 'number' &&
    typeof c.channels === 'number' &&
    typeof c.format === 'string' &&
    typeof c.frame_duration_ms === 'number'
  );
}

/**
 * Type guard verifying whether an object conforms to AudioFrame.
 */
export function isAudioFrame(obj: unknown): obj is AudioFrame {
  if (!obj || typeof obj !== 'object') return false;
  const f = obj as Record<string, unknown>;
  return (
    (typeof f.data === 'string' || f.data instanceof Uint8Array || f.data instanceof ArrayBuffer) &&
    typeof f.timestamp === 'number' &&
    typeof f.sample_rate === 'number' &&
    typeof f.frame_index === 'number' &&
    typeof f.is_speech === 'boolean'
  );
}

/**
 * Type guard verifying whether an object conforms to EventEnvelope.
 */
export function isEventEnvelope(obj: unknown): obj is EventEnvelope {
  if (!obj || typeof obj !== 'object') return false;
  const e = obj as Record<string, unknown>;
  return (
    typeof e.event_id === 'string' &&
    typeof e.event_type === 'string' &&
    typeof e.schema_version === 'string' &&
    typeof e.session_id === 'string' &&
    typeof e.correlation_id === 'string' &&
    typeof e.timestamp === 'string' &&
    typeof e.producer === 'string' &&
    typeof e.payload === 'object' &&
    e.payload !== null
  );
}
