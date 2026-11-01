/**
 * TypeScript Type Definitions for Speech-to-Text Module
 * 
 * Fulfills ClickUp deliverable: "Transcript Schemas: TypeScript definitions"
 * Shared with Frontend for full compile-time type safety without 'any'.
 */

export type AccumulatorState = 'IDLE' | 'ACCUMULATING' | 'PAUSED' | 'FINALIZED';

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
  event_type: 'transcript.segment' | 'transcript.utterance' | 'transcript.state_change';
  session_id: string;
  segment?: TranscriptSegment;
  utterance?: AccumulatedUtterance;
  state?: AccumulatorState;
  timestamp: number;
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
