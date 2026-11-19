export interface APIErrorDetail {
  code: string;
  message: string;
  request_id: string;
  details?: Record<string, unknown>;
}

export interface StandardResponse<T> {
  success: boolean;
  data?: T;
  error?: APIErrorDetail;
  timestamp: number;
}

export interface SessionData {
  session_id: string;
  status: string;
  created_at: number;
}

export interface ChatResponseData {
  request_id: string;
  status: string;
  response: string;
  requires_approval: boolean;
}

export interface HealthData {
  status: string;
  service: string;
  mock_mode: boolean;
}

export interface TranscriptSegment {
  id: string;
  text: string;
  confidence: number;
  start_time: number;
  end_time: number;
  is_final: boolean;
  revision?: number;
  speaker_id?: string;
}

export interface WindowContextData {
  app_name: string;
  window_title: string;
  app_type?: string;
  visible_snippet?: string;
}

export interface ContextSubmissionRequest {
  session_id: string;
  application?: string;
  window_title?: string;
  user_query?: string;
  screen_context?: string;
  active_window?: WindowContextData;
}

export interface ContextSubmissionData {
  context_id: string;
  status: string;
  relevant_context?: string;
}

/**
 * Standard inter-module event envelope as defined in backend schemas and integration contracts.
 */
export interface EventEnvelope<T = Record<string, unknown>> {
  event_id: string;
  event_type: string;
  schema_version: string;
  session_id: string;
  timestamp: string;
  producer: string;
  payload: T;
}

/**
 * Real-time SSE event stream connection status.
 */
export type EventStreamStatus = 'Connecting' | 'Connected' | 'Disconnected' | 'Error';

export interface EventStreamSubscriptionOptions {
  onEvent?: (event: EventEnvelope) => void;
  onStatusChange?: (status: EventStreamStatus) => void;
  onError?: (error: Error) => void;
  baseDelayMs?: number;
  backoffFactor?: number;
  maxDelayMs?: number;
  maxRetries?: number;
}

/**
 * Type-safe API Client for AcademiaAI / SDK-9 Voicebot Backend
 * Enforces zero 'any' types as required by enterprise standards.
 */
export class TypedVoicebotClient {
  constructor(private baseUrl: string = 'http://localhost:8000/api/v1') {}

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public async checkHealth(): Promise<StandardResponse<HealthData>> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) {
      throw new Error(`Health check failed with HTTP ${res.status}`);
    }
    return (await res.json()) as StandardResponse<HealthData>;
  }

  public async createSession(userId?: string): Promise<StandardResponse<SessionData>> {
    const res = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(userId ? { user_id: userId } : {}),
    });
    if (!res.ok) {
      throw new Error(`Create session failed with HTTP ${res.status}`);
    }
    const json = (await res.json()) as Record<string, unknown>;
    // Normalize if backend returned direct SessionResponse or wrapped StandardResponse
    if (json.session_id && !json.data) {
      return {
        success: true,
        data: {
          session_id: String(json.session_id),
          status: String(json.status || 'created'),
          created_at: typeof json.created_at === 'number' ? json.created_at : Date.now(),
        },
        timestamp: Date.now(),
      };
    }
    return json as unknown as StandardResponse<SessionData>;
  }

  public async sendChatMessage(sessionId: string, message: string): Promise<StandardResponse<ChatResponseData>> {
    const res = await fetch(`${this.baseUrl}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!res.ok) {
      throw new Error(`Send chat message failed with HTTP ${res.status}`);
    }
    return (await res.json()) as StandardResponse<ChatResponseData>;
  }

  public async submitContext(
    payload: ContextSubmissionRequest
  ): Promise<StandardResponse<ContextSubmissionData>> {
    const res = await fetch(`${this.baseUrl}/context`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(`Submit context failed with HTTP ${res.status}`);
    }
    return (await res.json()) as StandardResponse<ContextSubmissionData>;
  }

  public createMockContextResponse(
    payload: ContextSubmissionRequest
  ): StandardResponse<ContextSubmissionData> {
    return {
      success: true,
      data: {
        context_id: `ctx-mock-${Date.now()}`,
        status: 'mock_demo_accepted',
        relevant_context:
          payload.active_window?.visible_snippet ||
          `Mock context accepted for ${payload.application || 'application'}`,
      },
      timestamp: Date.now(),
    };
  }

  public getEventStreamUrl(sessionId: string): string {
    return `${this.baseUrl}/sessions/${sessionId}/events`;
  }

  public subscribeToSessionEvents(
    sessionId: string,
    options: EventStreamSubscriptionOptions = {}
  ): () => void {
    const {
      onEvent,
      onStatusChange,
      onError,
      baseDelayMs = 1000,
      backoffFactor = 2,
      maxDelayMs = 16000,
      maxRetries = 5,
    } = options;

    const url = this.getEventStreamUrl(sessionId);
    // Session-scoped deduplication set; preserved across reconnects, cleared only on unsubscribe/session close
    const seenEventIds = new Set<string>();

    let currentEventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let retryAttempt = 0;
    let isClosedByClient = false;

    // Verified event types from backend schemas and event producers
    const verifiedCustomEventTypes = [
      'session.status',
      'transcript.segment',
      'transcript.final',
      'workflow.plan',
      'workflow.step',
      'approval.request',
      'approval.decision',
    ];

    const handleEventData = (rawData: string) => {
      try {
        const parsed = JSON.parse(rawData) as EventEnvelope;
        if (parsed.event_id) {
          if (seenEventIds.has(parsed.event_id)) {
            // Deduplicate: ignore historical replayed event already processed
            return;
          }
          seenEventIds.add(parsed.event_id);
        }
        onEvent?.(parsed);
      } catch {
        // ignore unparseable data
      }
    };

    const handleMessageEvent = (event: MessageEvent) => {
      handleEventData(event.data);
    };

    const closeCurrentConnection = () => {
      if (currentEventSource) {
        verifiedCustomEventTypes.forEach((type) => {
          currentEventSource?.removeEventListener(type, handleMessageEvent as EventListener);
        });
        currentEventSource.close();
        currentEventSource = null;
      }
    };

    const scheduleReconnect = (err?: unknown) => {
      if (isClosedByClient) return;

      // Ensure old EventSource is closed before scheduling or creating replacement
      closeCurrentConnection();

      if (retryAttempt >= maxRetries) {
        onStatusChange?.('Error');
        onError?.(err instanceof Error ? err : new Error('EventSource maximum retries exceeded'));
        return;
      }

      onStatusChange?.('Connecting');

      const backoffDelay = Math.min(
        baseDelayMs * Math.pow(backoffFactor, retryAttempt),
        maxDelayMs
      );
      const jitter = Math.floor(Math.random() * 250);
      const delay = backoffDelay + jitter;
      retryAttempt++;

      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }

      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        if (!isClosedByClient) {
          connect();
        }
      }, delay);
    };

    const connect = () => {
      if (isClosedByClient) return;

      if (typeof EventSource === 'undefined') {
        onStatusChange?.('Connected');
        return;
      }

      closeCurrentConnection();
      onStatusChange?.('Connecting');

      try {
        const es = new EventSource(url);
        currentEventSource = es;

        es.onopen = () => {
          if (isClosedByClient) {
            closeCurrentConnection();
            return;
          }
          retryAttempt = 0;
          onStatusChange?.('Connected');
        };

        es.onerror = (err) => {
          if (isClosedByClient) return;
          scheduleReconnect(err);
        };

        es.onmessage = handleMessageEvent;

        verifiedCustomEventTypes.forEach((type) => {
          es.addEventListener(type, handleMessageEvent as EventListener);
        });
      } catch (err) {
        scheduleReconnect(err);
      }
    };

    if (typeof EventSource === 'undefined') {
      onStatusChange?.('Connecting');
      onStatusChange?.('Connected');
      return () => {
        onStatusChange?.('Disconnected');
      };
    }

    // Initial connection attempt
    connect();

    return () => {
      isClosedByClient = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      closeCurrentConnection();
      seenEventIds.clear();
      onStatusChange?.('Disconnected');
    };
  }
}
