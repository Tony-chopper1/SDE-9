export interface StandardResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    request_id: string;
    details?: Record<string, unknown>;
  };
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

export interface TranscriptSegment {
  id: string;
  text: string;
  confidence: number;
  start_time: number;
  end_time: number;
  is_final: boolean;
}

/**
 * Type-safe API Client for SDK-9 FastAPI Backend
 * Enforces zero 'any' types as required by W6 deliverables.
 */
export class TypedVoicebotClient {
  constructor(private baseUrl: string = 'http://localhost:8000/api/v1') {}

  public async checkHealth(): Promise<StandardResponse<{ status: string; service: string; mock_mode: boolean }>> {
    const res = await fetch(`${this.baseUrl}/health`);
    return (await res.json()) as StandardResponse<{ status: string; service: string; mock_mode: boolean }>;
  }

  public async createSession(): Promise<StandardResponse<SessionData>> {
    const res = await fetch(`${this.baseUrl}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return (await res.json()) as StandardResponse<SessionData>;
  }

  public async sendChatMessage(sessionId: string, message: string): Promise<StandardResponse<ChatResponseData>> {
    const res = await fetch(`${this.baseUrl}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    return (await res.json()) as StandardResponse<ChatResponseData>;
  }
}
