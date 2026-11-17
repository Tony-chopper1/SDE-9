import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { ContextSourcePanel } from '../components/ContextSourcePanel';
import { TypedVoicebotClient } from '../api_client';

afterEach(() => {
  cleanup();
});

describe('ContextSourcePanel Component', () => {
  it('strictly defaults to Screen Context OFF and shows privacy-first notice', () => {
    const onToggle = vi.fn();
    render(
      <ContextSourcePanel
        isScreenContextEnabled={false}
        onToggleScreenContext={onToggle}
      />
    );

    const toggleBtn = screen.getByRole('switch');
    expect(toggleBtn.getAttribute('aria-checked')).toBe('false');

    expect(
      screen.getByText('Screen context is disabled. Only spoken audio input is captured.')
    ).toBeTruthy();
    expect(
      screen.getByText(/Privacy First: No screen contents/i)
    ).toBeTruthy();

    fireEvent.click(toggleBtn);
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('displays clearly labeled mock demonstration context when Screen Context is ON', () => {
    const onToggle = vi.fn();
    render(
      <ContextSourcePanel
        isScreenContextEnabled={true}
        onToggleScreenContext={onToggle}
      />
    );

    const toggleBtn = screen.getByRole('switch');
    expect(toggleBtn.getAttribute('aria-checked')).toBe('true');

    expect(screen.getByText('MOCK DEMO')).toBeTruthy();
    expect(screen.getByText(/Demonstration mode: Simulated application context/i)).toBeTruthy();
    expect(screen.getByText('Visual Studio Code')).toBeTruthy();
    expect(screen.getByText('app.py — SDK-9 Voicebot (Mock Context)')).toBeTruthy();
    expect(screen.getByText(/def handle_voice_query/i)).toBeTruthy();

    // Verify sources tags
    expect(screen.getByText(/Audio VAD Engine/i)).toBeTruthy();
    expect(screen.getByText(/Mock Window Sensor/i)).toBeTruthy();
    expect(screen.getByText(/Session History Turns/i)).toBeTruthy();
  });

  it('triggers manual context sync test via client and displays live backend success feedback', async () => {
    const mockClient = new TypedVoicebotClient();
    vi.spyOn(mockClient, 'submitContext').mockResolvedValueOnce({
      success: true,
      data: {
        context_id: 'ctx-test-1',
        status: 'accepted',
        relevant_context: 'VS Code app.py active mock context',
      },
      timestamp: Date.now(),
    });

    render(
      <ContextSourcePanel
        isScreenContextEnabled={true}
        onToggleScreenContext={vi.fn()}
        client={mockClient}
      />
    );

    const syncBtn = screen.getByRole('button', { name: 'Test Context Sync with API' });
    fireEvent.click(syncBtn);

    await waitFor(() => {
      expect(screen.getByText('LIVE')).toBeTruthy();
      expect(screen.getByText(/Context accepted by server/i)).toBeTruthy();
      expect(screen.getByText(/Last synced:/i)).toBeTruthy();
    });
  });

  it('provides clearly labelled mock demo mode response when backend is unavailable (Failed to fetch)', async () => {
    const mockClient = new TypedVoicebotClient();
    // Simulate browser network failure when backend is offline
    vi.spyOn(mockClient, 'submitContext').mockRejectedValueOnce(
      new TypeError('Failed to fetch')
    );

    render(
      <ContextSourcePanel
        isScreenContextEnabled={true}
        onToggleScreenContext={vi.fn()}
        client={mockClient}
      />
    );

    const syncBtn = screen.getByRole('button', { name: 'Test Context Sync with API' });
    fireEvent.click(syncBtn);

    await waitFor(() => {
      // Check MOCK DEMO badge is displayed
      const demoBadges = screen.getAllByText('MOCK DEMO');
      expect(demoBadges.length).toBeGreaterThanOrEqual(2);
      expect(
        screen.getByText(/Mock Demo Mode: Context processed locally \(Backend server offline\)/i)
      ).toBeTruthy();
      expect(screen.getByText(/Last synced:/i)).toBeTruthy();
    });
  });

  it('handles and displays error message on actual API failure (HTTP 500 error)', async () => {
    const mockClient = new TypedVoicebotClient();
    vi.spyOn(mockClient, 'submitContext').mockRejectedValueOnce(
      new Error('Submit context failed with HTTP 500')
    );

    render(
      <ContextSourcePanel
        isScreenContextEnabled={true}
        onToggleScreenContext={vi.fn()}
        client={mockClient}
      />
    );

    const syncBtn = screen.getByRole('button', { name: 'Test Context Sync with API' });
    fireEvent.click(syncBtn);

    await waitFor(() => {
      const alert = screen.getByRole('alert');
      expect(alert.textContent).toContain('Submit context failed with HTTP 500');
    });
  });
});
