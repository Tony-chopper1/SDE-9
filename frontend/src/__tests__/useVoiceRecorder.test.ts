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
  let createdMediaRecorder: MockMediaRecorder | null = null;

  class MockMediaRecorder {
    state: string = 'inactive';
    start = vi.fn(() => {
      this.state = 'recording';
    });
    pause = vi.fn(() => {
      this.state = 'paused';
    });
    resume = vi.fn(() => {
      this.state = 'recording';
    });
    stop = vi.fn(() => {
      this.state = 'inactive';
      this.onstop?.(new Event('stop'));
    });
    ondataavailable: ((event: BlobEvent) => void) | null = null;
    onstop: ((event: Event) => void) | null = null;

    constructor() {
      createdMediaRecorder = this;
    }
  }

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
    createdMediaRecorder = null;
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });

    vi.stubGlobal('SpeechRecognition', MockRecognition);
    vi.stubGlobal('MediaRecorder', MockMediaRecorder);
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

  it('handles pause and resume of voice recording correctly', async () => {
    const { result } = renderHook(() => useVoiceRecorder());

    await act(async () => {
      await result.current.startRecording();
    });

    expect(result.current.recordingState).toBe('recording');
    expect(result.current.isPaused).toBe(false);
    expect(result.current.isRecording).toBe(true);
    expect(createdMediaRecorder?.state).toBe('recording');

    // Pause recording
    act(() => {
      result.current.pauseRecording();
    });

    expect(result.current.recordingState).toBe('paused');
    expect(result.current.isPaused).toBe(true);
    expect(result.current.isRecording).toBe(true);
    expect(createdMediaRecorder?.pause).toHaveBeenCalled();

    // Resume recording
    act(() => {
      result.current.resumeRecording();
    });

    expect(result.current.recordingState).toBe('recording');
    expect(result.current.isPaused).toBe(false);
    expect(createdMediaRecorder?.resume).toHaveBeenCalled();

    // Stop recording
    act(() => {
      result.current.stopRecording();
    });

    expect(result.current.recordingState).toBe('idle');
    expect(result.current.isRecording).toBe(false);
  });

  it('tracks interim revisions without changing the active segment ID', async () => {
    const segmentUpdates: unknown[] = [];
    const { result } = renderHook(() =>
      useVoiceRecorder({
        onSegmentUpdate: (seg) => segmentUpdates.push({ ...seg }),
      })
    );

    await act(async () => {
      await result.current.startRecording();
    });

    // 1st interim result
    act(() => {
      if (createdRecognition?.onresult) {
        createdRecognition.onresult({
          resultIndex: 0,
          results: [
            {
              isFinal: false,
              length: 1,
              0: { transcript: 'Interim step one', confidence: 0.88 },
            },
          ],
        } as unknown as SpeechRecognitionEvent);
      }
    });

    expect(result.current.liveRevision).toBe(1);
    expect(result.current.currentSegment?.revision).toBe(1);
    expect(result.current.currentSegment?.is_final).toBe(false);
    const activeSegmentId = result.current.currentSegment?.id;
    expect(activeSegmentId).toBeTruthy();

    // 2nd interim refinement (same utterance)
    act(() => {
      if (createdRecognition?.onresult) {
        createdRecognition.onresult({
          resultIndex: 0,
          results: [
            {
              isFinal: false,
              length: 1,
              0: { transcript: 'Interim step one refined', confidence: 0.91 },
            },
          ],
        } as unknown as SpeechRecognitionEvent);
      }
    });

    expect(result.current.liveRevision).toBe(2);
    expect(result.current.currentSegment?.revision).toBe(2);
    // Segment ID should NOT change across revisions of same segment!
    expect(result.current.currentSegment?.id).toBe(activeSegmentId);

    // Final result
    act(() => {
      if (createdRecognition?.onresult) {
        createdRecognition.onresult({
          resultIndex: 0,
          results: [
            {
              isFinal: true,
              length: 1,
              0: { transcript: 'Interim step one completed.', confidence: 0.97 },
            },
          ],
        } as unknown as SpeechRecognitionEvent);
      }
    });

    expect(result.current.currentSegment?.is_final).toBe(true);
    expect(result.current.currentSegment?.id).toBe(activeSegmentId);
  });

  it('preserves transcripts across pause and resume without text loss or duplicate segments', async () => {
    const onSessionComplete = vi.fn();
    const { result } = renderHook(() => useVoiceRecorder({ onSessionComplete }));

    await act(async () => {
      await result.current.startRecording();
    });

    // Speak first sentence
    act(() => {
      if (createdRecognition?.onresult) {
        createdRecognition.onresult({
          resultIndex: 0,
          results: [
            {
              isFinal: true,
              length: 1,
              0: { transcript: 'First sentence before pause.', confidence: 0.98 },
            },
          ],
        } as unknown as SpeechRecognitionEvent);
      }
    });

    expect(result.current.liveTranscript).toBe('First sentence before pause.');

    // Pause recording
    act(() => {
      result.current.pauseRecording();
    });
    expect(result.current.recordingState).toBe('paused');

    // Resume recording
    act(() => {
      result.current.resumeRecording();
    });
    expect(result.current.recordingState).toBe('recording');

    // Speak second sentence after resume
    act(() => {
      if (createdRecognition?.onresult) {
        createdRecognition.onresult({
          resultIndex: 0,
          results: [
            {
              isFinal: true,
              length: 1,
              0: { transcript: 'Second sentence after resume.', confidence: 0.96 },
            },
          ],
        } as unknown as SpeechRecognitionEvent);
      }
    });

    expect(result.current.liveTranscript).toBe(
      'First sentence before pause. Second sentence after resume.'
    );

    // Stop recording
    act(() => {
      result.current.stopRecording();
    });

    expect(onSessionComplete).toHaveBeenCalledWith(
      'First sentence before pause. Second sentence after resume.'
    );
  });
});
