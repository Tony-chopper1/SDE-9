
/* @vitest-environment jsdom */

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
} from '@testing-library/react';

import { App } from '../App';

beforeEach(() => {
  // Simulate microphone access
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: vi.fn().mockResolvedValue({
        getTracks: () => [{ stop: vi.fn() }],
      }),
    },
  });

  // Simulate the browser's MediaRecorder
  vi.stubGlobal(
    'MediaRecorder',
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
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('App component', () => {
  it('displays the Start Voice Capture button', () => {
    render(<App />);

    expect(
      screen.getByRole('button', { name: 'Start Voice Capture' })
    ).toBeTruthy();
  });

  it('changes the button text when clicked', async () => {
    render(<App />);

    const button = screen.getByRole('button', {
      name: 'Start Voice Capture',
    });

    fireEvent.click(button);

    expect(
      await screen.findByRole('button', { name: 'Stop Recording' })
    ).toBeTruthy();
  });

  it('displays the transcript', () => {
    render(<App />);

    expect(
      screen.getByText('SDK-9 AI Voice Co-Pilot active.')
    ).toBeTruthy();
  });
});
