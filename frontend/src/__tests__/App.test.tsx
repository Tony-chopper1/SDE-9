import {
  describe,
  it,
  expect,
  afterEach,
  beforeEach,
  vi,
} from 'vitest';
import {
  render,
  screen,
  fireEvent,
  cleanup,
  waitFor,
} from '@testing-library/react';
import { App } from '../App';

class FakeMediaRecorder {
  state: RecordingState = 'inactive';
  mimeType = 'audio/webm';
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.onstop?.(new Event('stop'));
  }
}

class FakeSpeechRecognition {
  lang = 'en-US';
  continuous = true;
  interimResults = true;
  onresult: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onend: (() => void) | null = null;

  start() {}
  stop() {
    this.onend?.();
  }
  abort() {}
}

describe('App Component', () => {
  let localStorageStore: Record<string, string> = {};

  beforeEach(() => {
    localStorageStore = {};
    const mockStorage = {
      getItem: vi.fn((key: string) => localStorageStore[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        localStorageStore[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete localStorageStore[key];
      }),
      clear: vi.fn(() => {
        localStorageStore = {};
      }),
      length: 0,
      key: vi.fn(),
    };

    Object.defineProperty(window, 'localStorage', {
      value: mockStorage,
      writable: true,
      configurable: true,
    });

    // Mock navigator.mediaDevices.getUserMedia
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: vi.fn() }],
        }),
      },
    });

    // Mock MediaRecorder
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);

    // Mock SpeechRecognition
    vi.stubGlobal('SpeechRecognition', FakeSpeechRecognition);

    // Prevent JSDOM navigation error on download link click
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders enterprise brand, navigation, and initial state', () => {
    render(<App />);

    expect(screen.getByText('AcademiaAI')).toBeTruthy();
    expect(screen.getByText('SYSTEM READY')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: 'Start Voice Capture' })
    ).toBeTruthy();
    expect(
      screen.getByRole('menuitem', { name: /Voice Studio/i })
    ).toBeTruthy();
    expect(
      screen.getByRole('menuitem', { name: /Session History/i })
    ).toBeTruthy();
  });

  it('toggles recording state when capture button is clicked', async () => {
    render(<App />);

    const button = screen.getByRole('button', {
      name: 'Start Voice Capture',
    });

    fireEvent.click(button);

    const stopButton = await screen.findByRole('button', {
      name: 'Stop Recording',
    });
    expect(stopButton).toBeTruthy();

    fireEvent.click(stopButton);

    const startButtonAgain = await screen.findByRole('button', {
      name: 'Start Voice Capture',
    });
    expect(startButtonAgain).toBeTruthy();
  });

  it('handles microphone permission denial gracefully', async () => {
    const notAllowedError = new Error('Permission denied');
    notAllowedError.name = 'NotAllowedError';

    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(notAllowedError),
      },
    });

    render(<App />);

    const button = screen.getByRole('button', {
      name: 'Start Voice Capture',
    });

    fireEvent.click(button);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert.textContent).toContain('Microphone permission was denied');
    });
  });

  it('loads and manages session history from localStorage', async () => {
    const mockSessions = [
      {
        id: 'session-saved-1',
        date: '10/31/2026, 10:00:00 AM',
        transcript: 'Previously saved transcript test content.',
      },
    ];

    localStorageStore['academia-voice-history'] = JSON.stringify(mockSessions);

    render(<App />);

    // Session should be visible in history list
    expect(screen.getByText('Previously saved transcript test content.')).toBeTruthy();

    // Select the session
    const selectBtn = screen.getByRole('button', {
      name: /Recording session #1/i,
    });
    fireEvent.click(selectBtn);

    // Title should switch to saved session
    expect(screen.getByText('Saved Session Transcript')).toBeTruthy();

    // Click back to live session
    const backBtn = screen.getByRole('button', { name: /Return to live recording view/i });
    fireEvent.click(backBtn);

    expect(screen.getByText('Transcript Timeline')).toBeTruthy();
  });

  it('allows deleting a session after confirmation', async () => {
    const mockSessions = [
      {
        id: 'session-to-delete',
        date: '10/31/2026, 11:00:00 AM',
        transcript: 'Session to be deleted.',
      },
    ];

    localStorageStore['academia-voice-history'] = JSON.stringify(mockSessions);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<App />);

    expect(screen.getByText('Session to be deleted.')).toBeTruthy();

    const deleteBtn = screen.getByRole('button', {
      name: /Delete session #1/i,
    });

    fireEvent.click(deleteBtn);

    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByText('Session to be deleted.')).toBeNull();
    });
  });

  it('handles transcript download action', () => {
    render(<App />);

    const createObjectURLSpy = vi.fn().mockReturnValue('blob:mock-url');
    const revokeObjectURLSpy = vi.fn();
    window.URL.createObjectURL = createObjectURLSpy;
    window.URL.revokeObjectURL = revokeObjectURLSpy;

    const exportBtn = screen.getByRole('button', {
      name: /Download current transcript as text file/i,
    });

    fireEvent.click(exportBtn);

    expect(createObjectURLSpy).toHaveBeenCalled();
  });

  it('allows navigating between workspace sidebar tabs', () => {
    render(<App />);

    const historyTab = screen.getByRole('menuitem', { name: /Session History/i });
    fireEvent.click(historyTab);

    expect(historyTab.getAttribute('aria-current')).toBe('page');
    expect(screen.getByText('RECORDING HISTORY')).toBeTruthy();
  });
});
