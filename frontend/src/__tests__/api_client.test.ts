import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TypedVoicebotClient, EventEnvelope } from '../api_client';

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
}

describe('TypedVoicebotClient', () => {
  let client: TypedVoicebotClient;
  const mockBaseUrl = 'http://localhost:8000/api/v1';

  beforeEach(() => {
    MockEventSource.instances = [];
    client = new TypedVoicebotClient(mockBaseUrl);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe('constructor and baseUrl', () => {
    it('uses default baseUrl when not specified', () => {
      const defaultClient = new TypedVoicebotClient();
      expect(defaultClient.getBaseUrl()).toBe('http://localhost:8000/api/v1');
    });

    it('uses custom baseUrl when provided', () => {
      const customClient = new TypedVoicebotClient('https://api.voicebot.example.com/v1');
      expect(customClient.getBaseUrl()).toBe('https://api.voicebot.example.com/v1');
    });
  });

  describe('checkHealth()', () => {
    it('returns health payload on successful 200 response', async () => {
      const mockPayload = {
        success: true,
        data: {
          status: 'healthy',
          service: 'sdk-9-voicebot',
          mock_mode: true,
        },
        timestamp: 1730000000,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockPayload,
      } as Response);

      const result = await client.checkHealth();

      expect(globalThis.fetch).toHaveBeenCalledWith(`${mockBaseUrl}/health`);
      expect(result.success).toBe(true);
      expect(result.data?.status).toBe('healthy');
      expect(result.data?.service).toBe('sdk-9-voicebot');
      expect(result.data?.mock_mode).toBe(true);
    });

    it('throws error when health check fails with non-200 HTTP status', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 503,
      } as Response);

      await expect(client.checkHealth()).rejects.toThrow(
        'Health check failed with HTTP 503'
      );
    });
  });

  describe('createSession()', () => {
    it('sends POST request and returns session data on success', async () => {
      const mockPayload = {
        success: true,
        data: {
          session_id: 'session-xyz-123',
          status: 'active',
          created_at: 1730000000,
        },
        timestamp: 1730000000,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => mockPayload,
      } as Response);

      const result = await client.createSession();

      expect(globalThis.fetch).toHaveBeenCalledWith(`${mockBaseUrl}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      expect(result.success).toBe(true);
      expect(result.data?.session_id).toBe('session-xyz-123');
      expect(result.data?.status).toBe('active');
    });

    it('normalizes direct SessionResponse from FastAPI backend', async () => {
      const directBackendPayload = {
        session_id: '550e8400-e29b-41d4-a716-446655440000',
        status: 'created',
        created_at: '2026-11-15T10:00:00Z',
        updated_at: '2026-11-15T10:00:00Z',
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => directBackendPayload,
      } as Response);

      const result = await client.createSession('user-01');

      expect(globalThis.fetch).toHaveBeenCalledWith(`${mockBaseUrl}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'user-01' }),
      });
      expect(result.success).toBe(true);
      expect(result.data?.session_id).toBe('550e8400-e29b-41d4-a716-446655440000');
      expect(result.data?.status).toBe('created');
    });

    it('throws error when session creation fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as Response);

      await expect(client.createSession()).rejects.toThrow(
        'Create session failed with HTTP 500'
      );
    });
  });

  describe('sendChatMessage()', () => {
    it('sends POST request with session_id and message payload', async () => {
      const mockPayload = {
        success: true,
        data: {
          request_id: 'req-abc-999',
          status: 'completed',
          response: 'I analyzed the visible error and found a missing dependency.',
          requires_approval: false,
        },
        timestamp: 1730000000,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockPayload,
      } as Response);

      const result = await client.sendChatMessage('session-xyz-123', 'Why is this failing?');

      expect(globalThis.fetch).toHaveBeenCalledWith(`${mockBaseUrl}/ai/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: 'session-xyz-123',
          message: 'Why is this failing?',
        }),
      });
      expect(result.success).toBe(true);
      expect(result.data?.response).toContain('missing dependency');
      expect(result.data?.requires_approval).toBe(false);
    });

    it('throws error when chat request fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 501,
      } as Response);

      await expect(
        client.sendChatMessage('session-xyz-123', 'Hello')
      ).rejects.toThrow('Send chat message failed with HTTP 501');
    });
  });

  describe('submitContext() and createMockContextResponse()', () => {
    it('sends POST request with context payload to /context endpoint', async () => {
      const requestData = {
        session_id: 'session-xyz-123',
        application: 'VS Code',
        window_title: 'app.py — SDK-9 Voicebot',
        user_query: 'Explain this error',
        screen_context: 'Traceback (most recent call last): NameError',
      };

      const mockPayload = {
        success: true,
        data: {
          context_id: 'ctx-101',
          status: 'accepted',
          relevant_context: 'VS Code editor with active Python script',
        },
        timestamp: 1730000000,
      };

      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockPayload,
      } as Response);

      const result = await client.submitContext(requestData);

      expect(globalThis.fetch).toHaveBeenCalledWith(`${mockBaseUrl}/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData),
      });
      expect(result.success).toBe(true);
      expect(result.data?.context_id).toBe('ctx-101');
      expect(result.data?.relevant_context).toContain('VS Code');
    });

    it('throws error when context submission returns non-200 HTTP status', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as Response);

      await expect(
        client.submitContext({ session_id: 'session-xyz-123' })
      ).rejects.toThrow('Submit context failed with HTTP 500');
    });

    it('generates a typed mock context response when requested', () => {
      const mockResult = client.createMockContextResponse({
        session_id: 'session-mock-1',
        application: 'VS Code',
        active_window: {
          app_name: 'VS Code',
          window_title: 'app.py',
          visible_snippet: 'console.log("hello")',
        },
      });

      expect(mockResult.success).toBe(true);
      expect(mockResult.data?.status).toBe('mock_demo_accepted');
      expect(mockResult.data?.relevant_context).toContain('console.log');
    });
  });

  describe('getEventStreamUrl() and subscribeToSessionEvents()', () => {
    it('constructs correct SSE endpoint URL from session ID', () => {
      const url = client.getEventStreamUrl('session-test-456');
      expect(url).toBe('http://localhost:8000/api/v1/sessions/session-test-456/events');
    });

    it('manages EventSource connection lifecycle and emits parsed event envelopes', () => {
      let createdEventSource: MockEventSource | null = null;
      vi.stubGlobal('EventSource', class extends MockEventSource {
        constructor(url: string) {
          super(url);
          createdEventSource = this;
        }
      });

      const onStatusChange = vi.fn();
      const onEvent = vi.fn();
      const onError = vi.fn();

      const unsubscribe = client.subscribeToSessionEvents('session-test-789', {
        onStatusChange,
        onEvent,
        onError,
        maxRetries: 0,
      });

      expect(onStatusChange).toHaveBeenCalledWith('Connecting');
      expect(createdEventSource).not.toBeNull();
      expect(createdEventSource!.url).toBe('http://localhost:8000/api/v1/sessions/session-test-789/events');

      // Trigger open event
      createdEventSource!.onopen?.();
      expect(onStatusChange).toHaveBeenCalledWith('Connected');

      // Trigger standard message event
      const sampleEnvelope: EventEnvelope = {
        event_id: 'evt-111',
        event_type: 'session.status',
        schema_version: '1.0',
        session_id: 'session-test-789',
        timestamp: '2026-11-15T10:00:00Z',
        producer: 'backend',
        payload: { status: 'active' },
      };

      createdEventSource!.onmessage?.({
        data: JSON.stringify(sampleEnvelope),
      } as MessageEvent);

      expect(onEvent).toHaveBeenCalledWith(sampleEnvelope);

      // Trigger custom named event listener (e.g. transcript.segment)
      const transcriptEnvelope: EventEnvelope = {
        event_id: 'evt-222',
        event_type: 'transcript.segment',
        schema_version: '1.0',
        session_id: 'session-test-789',
        timestamp: '2026-11-15T10:00:01Z',
        producer: 'speech_to_text',
        payload: { text: 'Hello world' },
      };

      const customListeners = createdEventSource!.listeners['transcript.segment'] || [];
      expect(customListeners.length).toBeGreaterThan(0);
      customListeners[0]({
        data: JSON.stringify(transcriptEnvelope),
      } as MessageEvent);

      expect(onEvent).toHaveBeenCalledWith(transcriptEnvelope);

      // Trigger error event
      createdEventSource!.onerror?.(new Event('error'));
      expect(onStatusChange).toHaveBeenCalledWith('Error');
      expect(onError).toHaveBeenCalled();

      // Trigger unsubscribe cleanup
      unsubscribe();
      expect(createdEventSource!.closed).toBe(true);
      expect(onStatusChange).toHaveBeenCalledWith('Disconnected');
    });

    it('reconnects with exponential backoff and closes old EventSource before creating replacement', () => {
      vi.useFakeTimers();
      vi.stubGlobal('EventSource', MockEventSource);

      const onStatusChange = vi.fn();
      const onError = vi.fn();

      const unsubscribe = client.subscribeToSessionEvents('session-reconnect-1', {
        onStatusChange,
        onError,
        baseDelayMs: 1000,
        backoffFactor: 2,
        maxDelayMs: 16000,
        maxRetries: 5,
      });

      expect(MockEventSource.instances.length).toBe(1);
      const firstSource = MockEventSource.instances[0];
      expect(firstSource.closed).toBe(false);

      firstSource.onopen?.();
      expect(onStatusChange).toHaveBeenCalledWith('Connected');

      // Trigger error on first connection
      firstSource.onerror?.(new Event('error'));

      // 1. Old EventSource must be immediately closed before replacement is created
      expect(firstSource.closed).toBe(true);
      expect(onStatusChange).toHaveBeenCalledWith('Connecting');

      // At this point, no second instance exists yet because backoff timer is pending
      expect(MockEventSource.instances.length).toBe(1);

      // Advance time by 1300ms (1000ms base + up to 250ms jitter)
      vi.advanceTimersByTime(1300);

      // Now second EventSource has been instantiated
      expect(MockEventSource.instances.length).toBe(2);
      const secondSource = MockEventSource.instances[1];
      expect(secondSource.closed).toBe(false);

      secondSource.onopen?.();
      expect(onStatusChange).toHaveBeenCalledWith('Connected');

      unsubscribe();
      expect(secondSource.closed).toBe(true);
      expect(onStatusChange).toHaveBeenCalledWith('Disconnected');
    });

    it('enforces maximum retry limits and reports Error when retries are exhausted', () => {
      vi.useFakeTimers();
      vi.stubGlobal('EventSource', MockEventSource);

      const onStatusChange = vi.fn();
      const onError = vi.fn();

      const unsubscribe = client.subscribeToSessionEvents('session-retry-limit', {
        onStatusChange,
        onError,
        baseDelayMs: 100,
        backoffFactor: 2,
        maxDelayMs: 1000,
        maxRetries: 2,
      });

      expect(MockEventSource.instances.length).toBe(1);

      // Attempt 1 fails
      MockEventSource.instances[0].onerror?.(new Event('error'));
      expect(MockEventSource.instances[0].closed).toBe(true);
      vi.advanceTimersByTime(400);

      // Attempt 2 fails
      expect(MockEventSource.instances.length).toBe(2);
      MockEventSource.instances[1].onerror?.(new Event('error'));
      expect(MockEventSource.instances[1].closed).toBe(true);
      vi.advanceTimersByTime(600);

      // Attempt 3 fails (reaches maxRetries: 2)
      expect(MockEventSource.instances.length).toBe(3);
      MockEventSource.instances[2].onerror?.(new Event('error'));
      expect(MockEventSource.instances[2].closed).toBe(true);

      // Status should be Error and onError called; no more EventSources created
      expect(onStatusChange).toHaveBeenCalledWith('Error');
      expect(onError).toHaveBeenCalled();

      vi.advanceTimersByTime(5000);
      expect(MockEventSource.instances.length).toBe(3);

      unsubscribe();
    });

    it('deduplicates replayed events across reconnections using event_id without eviction', () => {
      vi.useFakeTimers();
      vi.stubGlobal('EventSource', MockEventSource);

      const onEvent = vi.fn();

      const unsubscribe = client.subscribeToSessionEvents('session-dedup', {
        onEvent,
        baseDelayMs: 100,
        maxRetries: 3,
      });

      const firstSource = MockEventSource.instances[0];

      const eventA: EventEnvelope = {
        event_id: 'evt-repeat-1',
        event_type: 'session.status',
        schema_version: '1.0',
        session_id: 'session-dedup',
        timestamp: '2026-11-15T12:00:00Z',
        producer: 'backend',
        payload: { status: 'active' },
      };

      // First source receives eventA
      firstSource.onmessage?.({ data: JSON.stringify(eventA) } as MessageEvent);
      expect(onEvent).toHaveBeenCalledTimes(1);

      // Disconnection and reconnect
      firstSource.onerror?.(new Event('error'));
      vi.advanceTimersByTime(400);

      expect(MockEventSource.instances.length).toBe(2);
      const secondSource = MockEventSource.instances[1];

      // Second source receives historical replay of eventA from backend
      secondSource.onmessage?.({ data: JSON.stringify(eventA) } as MessageEvent);
      // onEvent is NOT called again! Still 1
      expect(onEvent).toHaveBeenCalledTimes(1);

      // Second source receives new eventB
      const eventB: EventEnvelope = {
        event_id: 'evt-repeat-2',
        event_type: 'transcript.segment',
        schema_version: '1.0',
        session_id: 'session-dedup',
        timestamp: '2026-11-15T12:00:05Z',
        producer: 'speech_to_text',
        payload: { text: 'New speech segment' },
      };
      secondSource.onmessage?.({ data: JSON.stringify(eventB) } as MessageEvent);
      expect(onEvent).toHaveBeenCalledTimes(2);

      unsubscribe();
    });

    it('cancels pending reconnection timers and closes EventSource on unsubscribe', () => {
      vi.useFakeTimers();
      vi.stubGlobal('EventSource', MockEventSource);

      const onStatusChange = vi.fn();

      const unsubscribe = client.subscribeToSessionEvents('session-cancel', {
        onStatusChange,
        baseDelayMs: 1000,
      });

      const firstSource = MockEventSource.instances[0];
      firstSource.onerror?.(new Event('error'));

      // Reconnect timer is pending; unsubscribe called immediately
      unsubscribe();
      expect(onStatusChange).toHaveBeenCalledWith('Disconnected');

      // Advance timers significantly
      vi.advanceTimersByTime(10000);

      // No new EventSource should ever be created
      expect(MockEventSource.instances.length).toBe(1);
    });

    it('falls back gracefully when EventSource is unavailable in environment', () => {
      // Remove EventSource from global
      vi.stubGlobal('EventSource', undefined);

      const onStatusChange = vi.fn();
      const unsubscribe = client.subscribeToSessionEvents('session-fallback', {
        onStatusChange,
      });

      expect(onStatusChange).toHaveBeenCalledWith('Connecting');
      expect(onStatusChange).toHaveBeenCalledWith('Connected');

      unsubscribe();
      expect(onStatusChange).toHaveBeenCalledWith('Disconnected');
    });
  });
});
