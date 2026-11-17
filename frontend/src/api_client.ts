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
 * Type-safe API Client for AcademiaAI / SDK-9 Voicebot Backend
 * Enforces zero 'any' types as required by W6 deliverables.
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

  public async createSession(): Promise<StandardResponse<SessionData>> {
    const res = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      throw new Error(`Create session failed with HTTP ${res.status}`);
    }
    return (await res.json()) as StandardResponse<SessionData>;
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
}
