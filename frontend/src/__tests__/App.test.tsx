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
  act,
  within,
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

class MockEventSource {
  public static instances: MockEventSource[] = [];
  public url: string;
  public onopen: (() => void) | null = null;
  public onerror: ((err: unknown) => void) | null = null;
  public onmessage: ((event: MessageEvent) => void) | null = null;
  public listeners: Record<string, ((event: MessageEvent) => void)[]> = {};
  public closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    queueMicrotask(() => {
      if (!this.closed && this.onopen) {
        this.onopen();
      }
    });
  }

  public addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners[type]) {
      this.listeners[type] = [];
    }
    this.listeners[type].push(listener);
  }

  public removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((l) => l !== listener);
    }
  }

  public close() {
    this.closed = true;
  }

  public simulateOpen() {
    this.onopen?.();
  }

  public simulateError(err?: unknown) {
    this.onerror?.(err ?? new Event('error'));
  }

  public simulateEvent(type: string, data: unknown) {
    const event = {
      data: typeof data === 'string' ? data : JSON.stringify(data),
      type,
    } as MessageEvent;
    if (this.listeners[type]) {
      this.listeners[type].forEach((l) => l(event));
    }
    if (type === 'message' && this.onmessage) {
      this.onmessage(event);
    }
  }
}

describe('App Component', () => {
  let localStorageStore: Record<string, string> = {};

  beforeEach(() => {
    localStorageStore = {};
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource);
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

    // Mock global fetch for health check and session creation
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes('/sessions')) {
        return {
          ok: true,
          status: 201,
          json: async () => ({
            session_id: 'test-session-uuid-1234',
            status: 'created',
            created_at: '2026-11-15T12:00:00Z',
            updated_at: '2026-11-15T12:00:00Z',
          }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: {
            status: 'healthy',
            service: 'sdk-9-voicebot',
            mock_mode: true,
          },
          timestamp: Date.now(),
        }),
      } as Response;
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders enterprise brand, navigation, and initial state', async () => {
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

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
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

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });

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

  it('handles transcript download action', async () => {
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

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
  });

  it('allows navigating between workspace sidebar tabs', async () => {
    render(<App />);

    const historyTab = screen.getByRole('menuitem', { name: /Session History/i });
    fireEvent.click(historyTab);

    expect(historyTab.getAttribute('aria-current')).toBe('page');
    expect(screen.getByText('RECORDING HISTORY')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
  });

  it('displays the Engine Status panel inside the sidebar with live health data', async () => {
    render(<App />);

    expect(screen.getByText('ENGINE STATUS')).toBeTruthy();
    expect(screen.getByText('Engine')).toBeTruthy();
    expect(screen.getByText('Latency')).toBeTruthy();
    expect(screen.getByText('Speech API')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
  });

  it('handles Pause, Resume, and Stop transitions in the UI', async () => {
    render(<App />);

    // Start Recording
    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    const pauseBtn = await screen.findByRole('button', { name: 'Pause Recording' });
    expect(pauseBtn).toBeTruthy();
    expect(screen.getByText('RECORDING')).toBeTruthy();

    // Pause
    fireEvent.click(pauseBtn);
    const resumeBtn = await screen.findByRole('button', { name: 'Resume Recording' });
    expect(resumeBtn).toBeTruthy();
    expect(screen.getByText('PAUSED')).toBeTruthy();

    // Resume
    fireEvent.click(resumeBtn);
    const pauseBtnAgain = await screen.findByRole('button', { name: 'Pause Recording' });
    expect(pauseBtnAgain).toBeTruthy();
    expect(screen.getByText('RECORDING')).toBeTruthy();

    // Stop
    const stopBtn = screen.getByRole('button', { name: 'Stop Recording' });
    fireEvent.click(stopBtn);

    const startBtnAgain = await screen.findByRole('button', { name: 'Start Voice Capture' });
    expect(startBtnAgain).toBeTruthy();
    expect(screen.getByText('STANDBY')).toBeTruthy();
  });

  it('supports keyboard shortcuts (Alt+R, Alt+P, Alt+C) and ignores them in text inputs', async () => {
    render(<App />);

    // Initial state: STANDBY, Screen Context OFF
    expect(screen.getByText('STANDBY')).toBeTruthy();
    const contextSwitch = screen.getByRole('switch');
    expect(contextSwitch.getAttribute('aria-checked')).toBe('false');

    // Alt+C toggles Screen Context ON
    fireEvent.keyDown(window, { key: 'c', altKey: true });
    expect(contextSwitch.getAttribute('aria-checked')).toBe('true');

    // Alt+C toggles Screen Context OFF
    fireEvent.keyDown(window, { key: 'c', altKey: true });
    expect(contextSwitch.getAttribute('aria-checked')).toBe('false');

    // Alt+R starts recording
    fireEvent.keyDown(window, { key: 'r', altKey: true });
    await screen.findByRole('button', { name: 'Pause Recording' });
    expect(screen.getByText('RECORDING')).toBeTruthy();

    // Alt+P pauses recording
    fireEvent.keyDown(window, { key: 'p', altKey: true });
    await screen.findByRole('button', { name: 'Resume Recording' });
    expect(screen.getByText('PAUSED')).toBeTruthy();

    // Alt+P resumes recording
    fireEvent.keyDown(window, { key: 'p', altKey: true });
    await screen.findByRole('button', { name: 'Pause Recording' });
    expect(screen.getByText('RECORDING')).toBeTruthy();

    // Verify shortcuts are ignored inside an input element
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: 'p', altKey: true });
    // Still recording because shortcut was ignored!
    expect(screen.getByText('RECORDING')).toBeTruthy();

    document.body.removeChild(input);

    // Alt+R stops recording
    fireEvent.keyDown(window, { key: 'r', altKey: true });
    await screen.findByRole('button', { name: 'Start Voice Capture' });
    expect(screen.getByText('STANDBY')).toBeTruthy();
  });

  it('renders the Context Source Panel with default OFF state and allows toggling to ON', async () => {
    render(<App />);

    // Default OFF
    expect(
      screen.getByText('Screen context is disabled. Only spoken audio input is captured.')
    ).toBeTruthy();

    const switchBtn = screen.getByRole('switch');
    fireEvent.click(switchBtn);

    // Now ON
    expect(screen.getByText('MOCK DEMO')).toBeTruthy();
    expect(screen.getByText('Visual Studio Code')).toBeTruthy();
    expect(screen.getByText('app.py — SDK-9 Voicebot (Mock Context)')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
  });

  it('displays the mock mode banner when backend reports mock_mode: true', async () => {
    render(<App />);

    await waitFor(() => {
      const banner = screen.getByRole('status', { name: 'Mock Mode Active' });
      expect(banner).toBeTruthy();
      expect(screen.getByText('MOCK MODE')).toBeTruthy();
      expect(
        screen.getByText(/Backend services are operating in simulated test mode/i)
      ).toBeTruthy();
    });
  });

  it('does not display the mock mode banner when backend reports mock_mode: false', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: {
          status: 'healthy',
          service: 'sdk-9-voicebot',
          mock_mode: false,
        },
        timestamp: Date.now(),
      }),
    } as Response);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });

    expect(screen.queryByRole('status', { name: 'Mock Mode Active' })).toBeNull();
    expect(screen.queryByText('MOCK MODE')).toBeNull();
  });

  it('does not display the mock mode banner when backend health check fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'));

    render(<App />);

    await waitFor(() => {
      expect(screen.queryByRole('status', { name: 'Mock Mode Active' })).toBeNull();
      expect(screen.queryByText('MOCK MODE')).toBeNull();
    });
  });

  it('displays the microphone permission badge in voice controls', async () => {
    render(<App />);

    const badge = screen.getByRole('status', {
      name: /Microphone permission:/i,
    });
    expect(badge).toBeTruthy();
    expect(badge.textContent).toContain('MIC:');

    await waitFor(() => {
      expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    });
  });
  it('creates a backend session and connects to the SSE event stream on recording start', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    // Verify Stop button appears and recording starts
    const stopBtn = await screen.findByRole('button', { name: 'Stop Recording' });
    expect(stopBtn).toBeTruthy();

    // Verify EventSource instance was created for the session SSE endpoint
    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
      const instance = MockEventSource.instances[0];
      expect(instance.url).toContain('/api/v1/sessions/test-session-uuid-1234/events');
    });

    // Verify stream status in AppShell pill and VoiceControls badge
    await waitFor(() => {
      const streamPill = screen.getByRole('status', {
        name: /Event stream connection status: Connected/i,
      });
      expect(streamPill).toBeTruthy();
      const streamBadge = screen.getByRole('status', {
        name: /Event stream: Connected/i,
      });
      expect(streamBadge).toBeTruthy();
    });

    // Simulate custom event on the SSE stream
    const stream = MockEventSource.instances[0];
    act(() => {
      stream.simulateEvent('session.status', {
      event_id: 'evt-test-1',
      event_type: 'session.status',
      schema_version: '1.0.0',
      session_id: 'test-session-uuid-1234',
      timestamp: Date.now(),
      producer: 'backend',
      payload: { status: 'active' },
      });
    });

    // Stop recording and verify SSE connection closes and status becomes Disconnected
    fireEvent.click(stopBtn);
    expect(stream.closed).toBe(true);

    await waitFor(() => {
      expect(
        screen.getByRole('status', {
          name: /Event stream connection status: Disconnected/i,
        })
      ).toBeTruthy();
    });
  });

  it('handles backend session creation error gracefully without breaking voice capture', async () => {
    // Session creation returns error
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes('/sessions')) {
        return {
          ok: false,
          status: 500,
          json: async () => ({ detail: 'Internal Server Error' }),
        } as Response;
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: { status: 'healthy', service: 'sdk-9-voicebot', mock_mode: true },
          timestamp: Date.now(),
        }),
      } as Response;
    });

    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    // Voice capture continues despite backend session failure
    const stopBtn = await screen.findByRole('button', { name: 'Stop Recording' });
    expect(stopBtn).toBeTruthy();

    // Stream status safely shows Error
    await waitFor(() => {
      expect(
        screen.getByRole('status', {
          name: /Event stream connection status: Error/i,
        })
      ).toBeTruthy();
      expect(
        screen.getByRole('status', {
          name: /Event stream: Error/i,
        })
      ).toBeTruthy();
    });

    // Stop recording gracefully
    fireEvent.click(stopBtn);
    await screen.findByRole('button', { name: 'Start Voice Capture' });
  });

  it('handles SSE connection error gracefully without crashing', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];
    // Simulate stream error event
    act(() => {
      stream.simulateError();
    });

    await waitFor(() => {
      // Old EventSource was closed and UI entered Connecting for exponential backoff retry
      expect(stream.closed).toBe(true);
      expect(
        screen.getByRole('status', {
          name: /Event stream connection status: Connecting/i,
        })
      ).toBeTruthy();
      expect(
        screen.getByRole('status', {
          name: /Event stream: Connecting/i,
        })
      ).toBeTruthy();
    });

    // Voice recording remains active and functional
    expect(screen.getByRole('button', { name: 'Stop Recording' })).toBeTruthy();
  });

  it('cleans up active SSE connection when component unmounts', async () => {
    const { unmount } = render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];
    expect(stream.closed).toBe(false);

    unmount();
    expect(stream.closed).toBe(true);
  });
  it('renders workflow progress card in standby mode and supports simulated mock plan trigger', async () => {
    render(<App />);

    // Standby state initially present
    expect(screen.getByText('AGENTIC WORKFLOW')).toBeTruthy();
    expect(screen.getByText('IDLE')).toBeTruthy();
    expect(screen.getAllByText(/No active workflow plan/i).length).toBeGreaterThan(0);

    // When mock mode is active, simulated demo trigger button is rendered
    await waitFor(() => {
      expect(screen.getByText('SIMULATED TESTING')).toBeTruthy();
    });

    const demoBtn = screen.getByRole('button', {
      name: /Load simulated demo workflow plan/i,
    });
    act(() => {
      fireEvent.click(demoBtn);
    });

    // Workflow card now renders simulated demo plan and steps
    expect(screen.getByText(/Scan workspace files, extract error metrics/i)).toBeTruthy();
    expect(screen.getByText('SIMULATED WORKFLOW (MOCK)')).toBeTruthy();
    expect(screen.getByText('Search workspace files for error diagnostic logs')).toBeTruthy();
    expect(screen.getByText('Read file content and extract latency samples')).toBeTruthy();
    expect(screen.getByText('Evaluate statistical median and error rate')).toBeTruthy();

    // Dismiss plan
    const dismissBtn = screen.getByRole('button', { name: 'Dismiss workflow plan' });
    act(() => {
      fireEvent.click(dismissBtn);
    });
    expect(screen.getByText('IDLE')).toBeTruthy();
  });

  it('updates workflow progress UI when receiving workflow.plan and workflow.step SSE events', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Simulate backend sending workflow.plan event
    const mockPlanEnvelope = {
      event_id: 'evt-plan-001',
      event_type: 'workflow.plan',
      schema_version: '1.0',
      session_id: 'test-session-uuid-1234',
      timestamp: '2026-11-15T12:00:00Z',
      producer: 'agent_orchestrator',
      payload: {
        plan_id: 'plan-live-001',
        session_id: 'test-session-uuid-1234',
        goal: 'Analyze system logs and verify database connections',
        steps: [
          {
            id: 'step-live-1',
            step_number: 1,
            description: 'Scan server log files',
            tool_name: 'file.search',
            safety_level: 'A',
            status: 'running',
          },
          {
            id: 'step-live-2',
            step_number: 2,
            description: 'Ping database replica endpoints',
            tool_name: 'network.ping',
            safety_level: 'B',
            status: 'pending',
          },
        ],
        current_step_index: 0,
        overall_safety_level: 'B',
        requires_approval: false,
        status: 'EXECUTING',
        created_at: 1731670000,
      },
    };

    act(() => {
      stream.simulateEvent('workflow.plan', mockPlanEnvelope);
    });

    await waitFor(() => {
      expect(screen.getByText('Analyze system logs and verify database connections')).toBeTruthy();
      expect(screen.getByText('Scan server log files')).toBeTruthy();
      expect(screen.getByText('Ping database replica endpoints')).toBeTruthy();
    });

    // Simulate backend sending workflow.step event completing step 1
    const mockStepEnvelope = {
      event_id: 'evt-step-002',
      event_type: 'workflow.step',
      schema_version: '1.0',
      session_id: 'test-session-uuid-1234',
      timestamp: '2026-11-15T12:00:02Z',
      producer: 'tool_executor',
      payload: {
        plan_id: 'plan-live-001',
        step_id: 'step-live-1',
        step_number: 1,
        status: 'completed',
        result: { found_logs: 3 },
      },
    };

    act(() => {
      stream.simulateEvent('workflow.step', mockStepEnvelope);
    });

    await waitFor(() => {
      const step1Badge = screen.getByRole('status', { name: 'Step 1 status: completed' });
      expect(step1Badge).toBeTruthy();
      expect(screen.getByText('50% Completed')).toBeTruthy();
    });
  });
  it('ignores workflow.step events belonging to a different plan_id', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Set active plan plan-A
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-A',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-A',
          session_id: 'test-session-uuid-1234',
          goal: 'Target Plan A Goal',
          steps: [
            {
              id: 'step-A1',
              step_number: 1,
              description: 'Step A1 pending',
              tool_name: 'tool.a',
              safety_level: 'A',
              status: 'pending',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'A',
          requires_approval: false,
          status: 'PENDING',
          created_at: 1731670000,
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Target Plan A Goal')).toBeTruthy();
      expect(screen.getByRole('status', { name: 'Step 1 status: pending' })).toBeTruthy();
    });

    // Send step event with a DIFFERENT plan_id: plan-B
    act(() => {
      stream.simulateEvent('workflow.step', {
        event_id: 'evt-step-B1',
        event_type: 'workflow.step',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'tool_executor',
        payload: {
          plan_id: 'plan-B',
          step_id: 'step-A1',
          step_number: 1,
          status: 'completed',
        },
      });
    });

    // Step 1 must REMAIN pending because plan_id did not match
    expect(screen.getByRole('status', { name: 'Step 1 status: pending' })).toBeTruthy();
  });

  it('does not mark plan completed while steps remain pending or running, and handles cancelled steps', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Initialize plan with 2 steps: 1 running, 1 pending
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-multi',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-safe-status',
          session_id: 'test-session-uuid-1234',
          goal: 'Safe status transition testing',
          steps: [
            {
              id: 's1',
              step_number: 1,
              description: 'Step 1 execution',
              tool_name: 'tool.one',
              safety_level: 'A',
              status: 'running',
            },
            {
              id: 's2',
              step_number: 2,
              description: 'Step 2 pending',
              tool_name: 'tool.two',
              safety_level: 'A',
              status: 'pending',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'A',
          requires_approval: false,
          status: 'EXECUTING',
          created_at: 1731670000,
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Safe status transition testing')).toBeTruthy();
    });

    // Complete step 1; step 2 is still pending so overall plan status must NOT be COMPLETED
    act(() => {
      stream.simulateEvent('workflow.step', {
        event_id: 'evt-step-s1-done',
        event_type: 'workflow.step',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'tool_executor',
        payload: {
          plan_id: 'plan-safe-status',
          step_id: 's1',
          step_number: 1,
          status: 'completed',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('status', { name: 'Overall plan status: EXECUTING' })).toBeTruthy();
    });

    // Cancel step 2; now step 1 is completed and step 2 is cancelled (no running or pending)
    act(() => {
      stream.simulateEvent('workflow.step', {
        event_id: 'evt-step-s2-cancel',
        event_type: 'workflow.step',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:02Z',
        producer: 'tool_executor',
        payload: {
          plan_id: 'plan-safe-status',
          step_id: 's2',
          step_number: 2,
          status: 'cancelled',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('status', { name: 'Overall plan status: CANCELLED' })).toBeTruthy();
    });
  });

  it('transitions overall plan status to FAILED or REJECTED when a step fails or is rejected', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Initialize plan with a running step
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-fail-test',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-fail-test',
          session_id: 'test-session-uuid-1234',
          goal: 'Failure and rejection testing',
          steps: [
            {
              id: 'step-f1',
              step_number: 1,
              description: 'Step to fail',
              tool_name: 'tool.failing',
              safety_level: 'B',
              status: 'running',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'B',
          requires_approval: false,
          status: 'EXECUTING',
          created_at: 1731670000,
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Failure and rejection testing')).toBeTruthy();
    });

    // Simulate step failure
    act(() => {
      stream.simulateEvent('workflow.step', {
        event_id: 'evt-step-f1-fail',
        event_type: 'workflow.step',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'tool_executor',
        payload: {
          plan_id: 'plan-fail-test',
          step_id: 'step-f1',
          step_number: 1,
          status: 'failed',
          error: 'Execution failed due to API timeout',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('status', { name: 'Overall plan status: FAILED' })).toBeTruthy();
      expect(screen.getByRole('alert').textContent).toContain('Execution failed due to API timeout');
    });

    // Simulate step rejection
    act(() => {
      stream.simulateEvent('workflow.step', {
        event_id: 'evt-step-f1-reject',
        event_type: 'workflow.step',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:02Z',
        producer: 'tool_executor',
        payload: {
          plan_id: 'plan-fail-test',
          step_id: 'step-f1',
          step_number: 1,
          status: 'rejected',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('status', { name: 'Overall plan status: REJECTED' })).toBeTruthy();
    });
  });

  it('displays approval dialog when receiving approval.request SSE event with safety info and risk details', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Establish active plan
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-appr-1',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-sens-1',
          session_id: 'test-session-uuid-1234',
          goal: 'Clean up diagnostic log archives',
          steps: [
            {
              id: 'step-sens-1',
              step_number: 1,
              description: 'Overwrite old archive file',
              tool_name: 'file.overwrite',
              safety_level: 'C',
              status: 'pending',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'C',
          requires_approval: true,
          status: 'PLANNING',
          created_at: 1731670000,
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Clean up diagnostic log archives')).toBeTruthy();
    });

    // Simulate approval.request SSE event
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-001',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-appr-101',
          plan_id: 'plan-sens-1',
          session_id: 'test-session-uuid-1234',
          safety_level: 'C',
          status: 'PENDING',
          action: 'Overwrite old archive file',
          tool_name: 'file.overwrite',
          step_number: 1,
          parameters: { target_path: '/logs/archive_2026.zip' },
        },
      });
    });

    // Verify dialog appears with safety information and risks
    await waitFor(() => {
      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeTruthy();
      expect(screen.getByText('Action Requires Authorization')).toBeTruthy();
      expect(screen.getAllByText('Overwrite old archive file').length).toBeGreaterThan(0);
      expect(within(dialog).getByText('file.overwrite')).toBeTruthy();
      expect(screen.getByText(/Level C – Sensitive/i)).toBeTruthy();
      expect(screen.getByText(/Sensitive Action: This operation modifies state/i)).toBeTruthy();
    });
  });

  it('allows approving an action request, updating plan status without claiming fake execution', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Establish plan
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-appr-2',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-appr-2',
          session_id: 'test-session-uuid-1234',
          goal: 'Deploy configuration update',
          steps: [
            {
              id: 'step-appr-2',
              step_number: 1,
              description: 'Write updated settings',
              tool_name: 'config.write',
              safety_level: 'C',
              status: 'pending',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'C',
          requires_approval: true,
          status: 'AWAITING_APPROVAL',
          created_at: 1731670000,
        },
      });
    });

    // Send approval.request
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-002',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-appr-102',
          plan_id: 'plan-appr-2',
          safety_level: 'C',
          action: 'Write updated settings',
          tool_name: 'config.write',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });

    // Approve the action
    const approveBtn = screen.getByRole('button', { name: /Approve requested action/i });
    act(() => {
      fireEvent.click(approveBtn);
    });

    // Dialog closes and overall plan status transitions to APPROVED
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(screen.getByRole('status', { name: 'Overall plan status: APPROVED' })).toBeTruthy();
    });
  });

  it('handles action rejection safely without ever triggering execution and halts workflow', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Establish plan
    act(() => {
      stream.simulateEvent('workflow.plan', {
        event_id: 'evt-plan-appr-3',
        event_type: 'workflow.plan',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'agent_orchestrator',
        payload: {
          plan_id: 'plan-appr-3',
          session_id: 'test-session-uuid-1234',
          goal: 'High impact file modification',
          steps: [
            {
              id: 'step-appr-3',
              step_number: 1,
              description: 'Dangerous file modification',
              tool_name: 'system.exec',
              safety_level: 'D',
              status: 'pending',
            },
          ],
          current_step_index: 0,
          overall_safety_level: 'D',
          requires_approval: true,
          status: 'AWAITING_APPROVAL',
          created_at: 1731670000,
        },
      });
    });

    // Send approval.request for destructive action
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-003',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-appr-103',
          plan_id: 'plan-appr-3',
          safety_level: 'D',
          action: 'Dangerous file modification',
          tool_name: 'system.exec',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
      expect(screen.getByText(/Level D – Destructive/i)).toBeTruthy();
    });

    // Type optional rejection reason
    const reasonInput = screen.getByLabelText(/Rejection Reason \(Optional\):/i);
    fireEvent.change(reasonInput, { target: { value: 'Privileged execution forbidden' } });

    // Reject the action
    const rejectBtn = screen.getByRole('button', { name: /Reject requested action/i });
    act(() => {
      fireEvent.click(rejectBtn);
    });

    // Verify dialog closes and plan & steps are marked REJECTED (execution strictly halted)
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(screen.getByRole('status', { name: 'Overall plan status: REJECTED' })).toBeTruthy();
      expect(screen.getByRole('status', { name: 'Step 1 status: rejected' })).toBeTruthy();
      expect(screen.getByText(/Action rejected by safety policy or operator/i)).toBeTruthy();
    });
  });

  it('handles Escape key by dismissing dialog without decision and renders review banner', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Send approval.request
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-004',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-appr-104',
          plan_id: 'plan-appr-4',
          safety_level: 'C',
          action: 'Sensitive directory scan',
          tool_name: 'dir.scan',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });

    // Press Escape to dismiss dialog without making decision
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });

    // Dialog is dismissed and pending review banner is shown
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(screen.getByRole('region', { name: 'Pending authorization request' })).toBeTruthy();
    });

    // Clicking Review Authorization reopens dialog
    const reviewBtn = screen.getByRole('button', { name: 'Review pending approval request' });
    act(() => {
      fireEvent.click(reviewBtn);
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });
  });

  it('ignores duplicate approval.request events for an already decided request_id', async () => {
    render(<App />);

    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(MockEventSource.instances.length).toBeGreaterThan(0);
    });

    const stream = MockEventSource.instances[0];

    // Send initial request
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-005',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:01Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-dup-test',
          plan_id: 'plan-dup',
          safety_level: 'C',
          action: 'Duplicate decision test action',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });

    // Reject it
    const rejectBtn = screen.getByRole('button', { name: /Reject requested action/i });
    act(() => {
      fireEvent.click(rejectBtn);
    });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    // Send duplicate event with identical request_id (e.g. from stream replay)
    act(() => {
      stream.simulateEvent('approval.request', {
        event_id: 'evt-req-005-replay',
        event_type: 'approval.request',
        schema_version: '1.0',
        session_id: 'test-session-uuid-1234',
        timestamp: '2026-11-15T12:00:02Z',
        producer: 'approval_manager',
        payload: {
          request_id: 'req-dup-test',
          plan_id: 'plan-dup',
          safety_level: 'C',
          action: 'Duplicate decision test action',
        },
      });
    });

    // Dialog remains closed because request was already decided
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
