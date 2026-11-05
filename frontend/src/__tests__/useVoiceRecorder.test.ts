import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVoiceRecorder } from '../hooks/useVoiceRecorder';
import {
  ISpeechRecognition,
  SpeechRecognitionEvent,
  SpeechRecognitionErrorEvent,
} from '../types/speech';

describe('useVoiceRecorder hook', () => {
  let createdRecognition: MockRecognition | null = null;

  class MockRecognition implements ISpeechRecognition {
    lang = 'en-US';
    continuous = true;
    interimResults = true;
    onresult: ((event: SpeechRecognitionEvent) => void) | null = null;
    onerror: ((event: SpeechRecognitionErrorEvent) => void) | null = null;
    onend: (() => void) | null = null;

    start = vi.fn();
    stop = vi.fn(() => {
      this.onend?.();
    });
    abort = vi.fn();

    constructor() {
      createdRecognition = this;
    }

    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    dispatchEvent = vi.fn().mockReturnValue(true);
  }

  beforeEach(() => {
    createdRecognition = null;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });

    vi.stubGlobal('SpeechRecognition', MockRecognition);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('accumulates speech recognition interim and final results', async () => {
    const onSessionComplete = vi.fn();
    const { result } = renderHook(() => useVoiceRecorder({ onSessionComplete }));

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.isRecording).toBe(true);
    expect(createdRecognition).toBeTruthy();

    // Simulate recognition onresult
    act(() => {
      if (createdRecognition?.onresult) {
        const mockEvent = {
          resultIndex: 0,
          results: [
            {
              isFinal: true,
              length: 1,
              0: { transcript: 'First final phrase.', confidence: 0.99 },
            },
          ],
        } as unknown as SpeechRecognitionEvent;
        createdRecognition.onresult(mockEvent);
      }
    });

    expect(result.current.liveTranscript).toBe('First final phrase.');

    // Stop recording and verify onSessionComplete callback
    act(() => {
      result.current.stopRecording();
    });

    expect(result.current.isRecording).toBe(false);
    expect(onSessionComplete).toHaveBeenCalledWith('First final phrase.');
  });

  it('handles speech recognition error event', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.startRecording();
    });

    act(() => {
      if (createdRecognition?.onerror) {
        const mockErr = {
          error: 'not-allowed',
        } as SpeechRecognitionErrorEvent;
        createdRecognition.onerror(mockErr);
      }
    });

    expect(result.current.errorMessage).toContain('Microphone permission was denied');
  });

  it('handles missing getUserMedia support gracefully', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: null,
    });

    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.isRecording).toBe(false);
    expect(result.current.errorMessage).toContain('Microphone access is not supported');
  });
});
