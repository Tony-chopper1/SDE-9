import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { EngineStatusPanel } from '../components/EngineStatusPanel';

afterEach(() => {
  cleanup();
});

describe('EngineStatusPanel Component', () => {
  it('renders default fallback state when status is unknown or empty', () => {
    render(<EngineStatusPanel />);

    expect(screen.getByText('ENGINE STATUS')).toBeTruthy();
    expect(screen.getAllByText('Not reported').length).toBe(2);
    expect(screen.getByText('—')).toBeTruthy();

    const engineVal = screen.getByLabelText('Engine: Not reported');
    expect(engineVal).toBeTruthy();

    const latencyVal = screen.getByLabelText('Latency: —');
    expect(latencyVal).toBeTruthy();

    const speechVal = screen.getByLabelText('Speech API: Not reported');
    expect(speechVal).toBeTruthy();
  });

  it('renders confirmed online values with green indicators when reported', () => {
    render(
      <EngineStatusPanel
        status={{
          engineName: 'sdk-9-voicebot',
          latencyMs: 28,
          speechApiStatus: 'online',
          speechApiLabel: 'Active',
          backendStatus: 'online',
        }}
      />
    );

    expect(screen.getByText('sdk-9-voicebot')).toBeTruthy();
    expect(screen.getByText('28 ms')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();

    const panelRegion = screen.getByRole('region', { name: /ENGINE STATUS/i });
    const greenDots = panelRegion.querySelectorAll('.dot-green');
    expect(greenDots.length).toBe(3);
  });

  it('renders offline/error indicators when backend or speech service fails', () => {
    render(
      <EngineStatusPanel
        status={{
          engineName: null,
          latencyMs: null,
          speechApiStatus: 'offline',
          speechApiLabel: 'Offline',
          backendStatus: 'offline',
        }}
      />
    );

    expect(screen.getByText('Not reported')).toBeTruthy();
    expect(screen.getByText('—')).toBeTruthy();
    expect(screen.getByText('Offline')).toBeTruthy();

    const panelRegion = screen.getByRole('region', { name: /ENGINE STATUS/i });
    const redDots = panelRegion.querySelectorAll('.dot-red');
    expect(redDots.length).toBe(3);
  });

  it('uses neutral dots for unknown or unavailable metrics', () => {
    render(
      <EngineStatusPanel
        status={{
          engineName: null,
          latencyMs: null,
          speechApiStatus: 'unknown',
          speechApiLabel: null,
          backendStatus: 'unknown',
        }}
      />
    );

    const panelRegion = screen.getByRole('region', { name: /ENGINE STATUS/i });
    const neutralDots = panelRegion.querySelectorAll('.dot-neutral');
    expect(neutralDots.length).toBe(3);
  });
});
