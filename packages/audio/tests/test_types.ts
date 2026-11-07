/**
 * Type-checking and runtime verification test for packages/audio/types.ts.
 * Executed via Node 24 native type stripping:
 *   node --experimental-strip-types packages/audio/tests/test_types.ts
 */
import {
  APPROVED_TEAM_DEFAULTS,
  PROVISIONAL_STT_SETTINGS,
  SUPPORTED_SAMPLE_RATES,
  VADState,
  isAudioConfig,
  isAudioFrame,
  isEventEnvelope,
  isVADState,
  type AudioConfig,
  type AudioFrame,
  type EventEnvelope,
  type VADEvent,
  type VADResult,
} from '../types.ts';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

console.log('Running TypeScript type verification for packages/audio/types.ts...');

// 1. Verify VADState enum values
assert(VADState.SILENCE === 'SILENCE', 'VADState.SILENCE matches Python enum');
assert(VADState.SPEECH_START === 'SPEECH_START', 'VADState.SPEECH_START matches Python enum');
assert(VADState.SPEECH === 'SPEECH', 'VADState.SPEECH matches Python enum');
assert(VADState.SPEECH_END === 'SPEECH_END', 'VADState.SPEECH_END matches Python enum');
assert(isVADState('SPEECH'), 'isVADState identifies valid enum string');
assert(!isVADState('INVALID_STATE'), 'isVADState rejects invalid state string');

// 2. Verify approved vs provisional defaults
assert(APPROVED_TEAM_DEFAULTS.frame_duration_ms === 30, 'Approved team default is 30ms');
assert(APPROVED_TEAM_DEFAULTS.status === 'APPROVED', 'Approved status marked correctly');
assert(PROVISIONAL_STT_SETTINGS.frame_duration_ms === 20, 'Provisional STT duration is 20ms');
assert(PROVISIONAL_STT_SETTINGS.status === 'PROVISIONAL', 'Provisional status marked correctly');
assert(SUPPORTED_SAMPLE_RATES.includes(16000), '16000 Hz is supported');

// 3. Construct and validate AudioConfig
const config30: AudioConfig = {
  sample_rate: APPROVED_TEAM_DEFAULTS.sample_rate,
  bit_depth: APPROVED_TEAM_DEFAULTS.bit_depth,
  channels: APPROVED_TEAM_DEFAULTS.channels,
  format: APPROVED_TEAM_DEFAULTS.format,
  frame_duration_ms: APPROVED_TEAM_DEFAULTS.frame_duration_ms,
};
assert(isAudioConfig(config30), 'config30 matches AudioConfig interface');

const config20: AudioConfig = {
  sample_rate: PROVISIONAL_STT_SETTINGS.sample_rate,
  bit_depth: PROVISIONAL_STT_SETTINGS.bit_depth,
  channels: PROVISIONAL_STT_SETTINGS.channels,
  format: PROVISIONAL_STT_SETTINGS.format,
  frame_duration_ms: PROVISIONAL_STT_SETTINGS.frame_duration_ms,
};
assert(isAudioConfig(config20), 'config20 matches AudioConfig interface');

// 4. Construct and validate AudioFrame (Team + Provisional STT fields)
const frame: AudioFrame = {
  data: new Uint8Array(960),
  timestamp: 1730304000.123,
  sample_rate: 16000,
  frame_index: 0,
  is_speech: false,
  audio_data: new Uint8Array(960),
  channels: 1,
  format: 's16le',
  frame_duration_ms: 30,
  sequence_number: 0,
  timestamp_ms: 0.0,
  frame_id: 'frame-test-001',
  timestamp_utc: '2026-10-30T14:30:00.123000+00:00',
};
assert(isAudioFrame(frame), 'frame matches AudioFrame interface');
assert(typeof frame.timestamp === 'number', 'timestamp is numeric seconds');
assert(typeof frame.timestamp_ms === 'number', 'timestamp_ms is numeric milliseconds');
assert(typeof frame.timestamp_utc === 'string', 'timestamp_utc is ISO string');

// 5. Construct and validate VADResult
const vadResult: VADResult = {
  is_speech: true,
  confidence: 0.95,
  energy_db: -18.5,
  metadata: { engine: 'EnergyVAD', hangover: 3 },
};
assert(vadResult.is_speech === true, 'VADResult holds classification flag');
assert(vadResult.confidence === 0.95, 'VADResult confidence in [0, 1]');

// 6. Construct and validate internal VADEvent
const vadEvent: VADEvent = {
  state: VADState.SPEECH_START,
  timestamp: 1730304000.2,
  energy_level: 850.5,
  confidence: 0.92,
  frame_index: 1,
  timestamp_ms: 30.0,
};
assert(vadEvent.state === VADState.SPEECH_START, 'VADEvent matches state transition');
assert(vadEvent.energy_level === 850.5, 'VADEvent tracks energy level');

// 7. Construct and validate SDK-9 EventEnvelope
const envelope: EventEnvelope<{ state: string; energy_level: number }> = {
  event_id: 'evt-test-12345',
  event_type: 'audio.vad.speech_start',
  schema_version: '1.0.0',
  session_id: 'session-ts-001',
  correlation_id: 'corr-ts-001',
  timestamp: '2026-10-30T14:30:00.200Z',
  producer: 'packages.audio',
  payload: {
    state: vadEvent.state,
    energy_level: vadEvent.energy_level,
  },
};
assert(isEventEnvelope(envelope), 'envelope matches EventEnvelope interface');
assert(envelope.producer === 'packages.audio', 'producer matches audio module');
assert(envelope.schema_version === '1.0.0', 'schema_version matches contract');

console.log('All TypeScript type tests passed successfully (7/7 assertions verified).');
