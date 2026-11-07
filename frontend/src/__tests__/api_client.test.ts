import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { TypedVoicebotClient } from '../api_client';

describe('TypedVoicebotClient', () => {
  let client: TypedVoicebotClient;
  const mockBaseUrl = 'http://localhost:8000/api/v1';

  beforeEach(() => {
    client = new TypedVoicebotClient(mockBaseUrl);
  });

  afterEach(() => {
    vi.restoreAllMocks();
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

    it('throws error when chat request returns 400 bad request', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 400,
      } as Response);

      await expect(
        client.sendChatMessage('session-xyz-123', '')
      ).rejects.toThrow('Send chat message failed with HTTP 400');
    });
  });
});
