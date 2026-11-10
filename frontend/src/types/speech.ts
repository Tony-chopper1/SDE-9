/**
 * Type declarations for Web Speech API and Media Recorder
 * Eliminates 'any' types across voice capture modules.
 */

export type MicPermissionState = 'prompt' | 'granted' | 'denied' | 'unsupported';

export interface SpeechRecognitionAlternativeItem {
  readonly transcript: string;
  readonly confidence: number;
}

export interface SpeechRecognitionResultItem {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: SpeechRecognitionAlternativeItem;
}

export interface SpeechRecognitionResultListWrapper {
  readonly length: number;
  [index: number]: SpeechRecognitionResultItem;
}

export interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListWrapper;
}

export interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string;
  readonly message?: string;
}

export interface ISpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

export interface ISpeechRecognitionConstructor {
  new (): ISpeechRecognition;
}

export interface RecordingSession {
  id: string;
  date: string;
  transcript: string;
  durationSeconds?: number;
}
