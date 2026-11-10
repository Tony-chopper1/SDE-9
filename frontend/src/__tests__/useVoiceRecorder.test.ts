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
    expect(result.current.micPermission).toBe('denied');
  });

  it('handles missing getUserMedia support gracefully and sets permission to unsupported', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: null,
    });

    const { result } = renderHook(() => useVoiceRecorder());

    expect(result.current.micPermission).toBe('unsupported');

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.isRecording).toBe(false);
    expect(result.current.errorMessage).toContain('Microphone access is not supported');
    expect(result.current.micPermission).toBe('unsupported');
  });

  it('initializes micPermission as prompt and transitions to granted upon successful getUserMedia', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    // Initially prompt (or fallback when permissions API not configured)
    expect(result.current.micPermission).toBe('prompt');

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.micPermission).toBe('granted');
  });

  it('transitions micPermission to denied when getUserMedia rejects with NotAllowedError', async () => {
    const deniedErr = new Error('Permission denied');
    deniedErr.name = 'NotAllowedError';

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(deniedErr),
      },
    });

    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.micPermission).toBe('denied');
    expect(result.current.errorMessage).toContain('Microphone permission was denied');
  });

  it('queries Permissions API when available and responds to permission changes', async () => {
    let changeListener: (() => void) | null = null;
    const fakeStatus = {
      state: 'prompt' as PermissionState,
      set onchange(fn: (() => void) | null) {
        changeListener = fn;
      },
      get onchange(): (() => void) | null {
        return changeListener;
      },
    };

    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: {
        query: vi.fn().mockResolvedValue(fakeStatus),
      },
    });

    const { result } = renderHook(() => useVoiceRecorder());

    // Wait for promise tick
    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.micPermission).toBe('prompt');

    // Simulate permission grant in browser
    act(() => {
      fakeStatus.state = 'granted';
      if (changeListener) {
        changeListener();
      }
    });

    expect(result.current.micPermission).toBe('granted');

    // Simulate permission denial in browser
    act(() => {
      fakeStatus.state = 'denied';
      if (changeListener) {
        changeListener();
      }
    });

    expect(result.current.micPermission).toBe('denied');
  });

  it('falls back to prompt when Permissions API query throws or is not supported', async () => {
    Object.defineProperty(navigator, 'permissions', {
      configurable: true,
      value: {
        query: vi.fn().mockRejectedValue(new Error('Query error')),
      },
    });

    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.micPermission).toBe('prompt');
  });
});
