/**
 * TypeScript Type Definitions for Speech-to-Text Module
 * 
 * Fulfills ClickUp deliverable: "Transcript Schemas: TypeScript definitions"
 * Shared with Frontend for full compile-time type safety without 'any'.
 */

export type AccumulatorState = 'IDLE' | 'ACCUMULATING' | 'PAUSED' | 'FINALIZED';

export type OrchestratorState = 'IDLE' | 'RUNNING' | 'PAUSED' | 'STOPPED' | 'ERROR';

export interface TranscriptSegment {
  id: string;
  text: string;
  confidence: number; // 0.0 to 1.0
  start_time: number; // in seconds
  end_time: number;   // in seconds
  is_final: boolean;
  speaker_id?: string;
  language?: string;
}

export interface AccumulatedUtterance {
  id: string;
  session_id: string;
  full_text: string;
  segments: TranscriptSegment[];
  start_time: number;
  end_time: number;
  duration: number;
  is_complete: boolean;
}

export interface TranscriptEvent {
  event_type:
    | 'transcript.segment'
    | 'transcript.interim'
    | 'transcript.final'
    | 'transcript.utterance'
    | 'transcript.state_change';
  session_id: string;
  segment?: TranscriptSegment;
  utterance?: AccumulatedUtterance;
  state?: AccumulatorState | OrchestratorState;
  timestamp: number;
}

/**
 * Standardized error envelope matching SDK-9 Integration Contract
 */
export interface STTErrorEnvelope {
  error: string;
  code:
    | 'STT_ERROR'
    | 'STT_TIMEOUT'
    | 'STT_PROVIDER_ERROR'
    | 'STT_CONNECTION_ERROR'
    | 'STT_RATE_LIMIT'
    | 'AUDIO_PREPROCESS_ERROR';
  timestamp: number;
  details?: Record<string, unknown>;
}

export interface AudioPreprocessorConfig {
  targetSampleRate?: number; // default: 16000
  targetPeakLevel?: number;  // default: 0.90
  enableNormalization?: boolean;
}

export interface RetryConfig {
  maxRetries?: number;
  baseBackoffSec?: number;
  maxBackoffSec?: number;
  backoffMultiplier?: number;
  jitter?: boolean;
  timeoutSec?: number;
}

/**
 * Interface contract for STT services (Mock or Production Whisper)
 */
export interface ITranscriberService {
  transcribe(audioData: Uint8Array | ArrayBuffer, phraseIndex?: number): Promise<TranscriptSegment[]>;
  simulateStreamingChunks?(phraseIndex?: number): AsyncGenerator<TranscriptSegment, void, unknown>;
}

/**
 * Interface contract for the Segment Accumulator State Machine
 */
export interface ISegmentAccumulator {
  readonly state: AccumulatorState;
  readonly count: number;
  addSegment(segment: TranscriptSegment): void;
  pause(): void;
  resume(): void;
  finalizeUtterance(): AccumulatedUtterance;
  clear(): void;
}

/**
 * Interface contract for the Transcript Reconciler
 */
export interface ITranscriptReconciler {
  readonly duplicateCount: number;
  readonly finalizedSegments: TranscriptSegment[];
  readonly activeInterim?: TranscriptSegment;
  processSegment(segment: TranscriptSegment): TranscriptEvent | null;
  getFullTranscript(): string;
  getFinalizedText(): string;
  flush(): TranscriptEvent | null;
  clear(): void;
}

/**
 * Interface contract for the STT Orchestrator
 */
export interface ISpeechToTextOrchestrator {
  readonly state: OrchestratorState;
  readonly totalFramesProcessed: number;
  readonly totalAudioBytesIngested: number;
  start(): void;
  pause(): void;
  resume(): void;
  pushAudio(audioData: Uint8Array | ArrayBuffer, sampleRate?: number, channels?: number): TranscriptEvent[];
  flush(): TranscriptEvent | null;
  finalizeUtterance(): AccumulatedUtterance;
  stop(): AccumulatedUtterance;
  getFullTranscript(): string;
}
