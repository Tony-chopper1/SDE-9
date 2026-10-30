
/* @vitest-environment jsdom */

import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { App } from '../App';

// Clear the rendered app after each test
afterEach(() => {
  cleanup();
});

describe('App component', () => {
  it('displays the Start Voice Capture button', () => {
    render(<App />);

    expect(
      screen.getByRole('button', { name: 'Start Voice Capture' })
    ).toBeTruthy();
  });

  it('changes the button text when clicked', () => {
    render(<App />);

    const button = screen.getByRole('button', {
      name: 'Start Voice Capture',
    });

    fireEvent.click(button);

    expect(
      screen.getByRole('button', { name: 'Stop Recording' })
    ).toBeTruthy();
  });

  it('displays the transcript', () => {
    render(<App />);

    expect(
      screen.getByText('SDK-9 AI Voice Co-Pilot active.')
    ).toBeTruthy();
  });
});
