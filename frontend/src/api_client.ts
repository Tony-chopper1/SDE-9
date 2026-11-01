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
}
