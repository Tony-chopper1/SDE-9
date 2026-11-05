import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { VoiceControls } from '../components/VoiceControls';

afterEach(() => {
  cleanup();
});

describe('VoiceControls Component', () => {
  it('renders STANDBY state with Start button and ready prompt', () => {
    const onToggle = vi.fn();
    render(
      <VoiceControls
        isRecording={false}
        recordingState="idle"
        onToggleRecording={onToggle}
      />
    );

    expect(screen.getByText('STANDBY')).toBeTruthy();
    expect(screen.getByText('Ready to capture audio')).toBeTruthy();
    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    expect(startBtn).toBeTruthy();

    fireEvent.click(startBtn);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('renders RECORDING state with Pause and Stop buttons and listening prompt', () => {
    const onPause = vi.fn();
    const onStop = vi.fn();
    const onToggle = vi.fn();

    render(
      <VoiceControls
        isRecording={true}
        recordingState="recording"
        onToggleRecording={onToggle}
        onPause={onPause}
        onStop={onStop}
      />
    );

    expect(screen.getByText('RECORDING')).toBeTruthy();
    expect(screen.getByText('Listening to your voice...')).toBeTruthy();

    const pauseBtn = screen.getByRole('button', { name: 'Pause Recording' });
    const stopBtn = screen.getByRole('button', { name: 'Stop Recording' });

    expect(pauseBtn).toBeTruthy();
    expect(stopBtn).toBeTruthy();

    fireEvent.click(pauseBtn);
    expect(onPause).toHaveBeenCalledTimes(1);

    fireEvent.click(stopBtn);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('renders PAUSED state with Resume and Stop buttons and paused prompt', () => {
    const onResume = vi.fn();
    const onStop = vi.fn();

    render(
      <VoiceControls
        isRecording={true}
        recordingState="paused"
        isPaused={true}
        onToggleRecording={vi.fn()}
        onResume={onResume}
        onStop={onStop}
      />
    );

    expect(screen.getByText('PAUSED')).toBeTruthy();
    expect(screen.getByText('Recording paused')).toBeTruthy();

    const resumeBtn = screen.getByRole('button', { name: 'Resume Recording' });
    const stopBtn = screen.getByRole('button', { name: 'Stop Recording' });

    expect(resumeBtn).toBeTruthy();
    expect(stopBtn).toBeTruthy();

    fireEvent.click(resumeBtn);
    expect(onResume).toHaveBeenCalledTimes(1);

    fireEvent.click(stopBtn);
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it('displays loading state during microphone initialization and disables action buttons', () => {
    render(
      <VoiceControls
        isRecording={false}
        recordingState="idle"
        isLoading={true}
        onToggleRecording={vi.fn()}
      />
    );

    expect(screen.getByText('Accessing microphone...')).toBeTruthy();
    const startBtn = screen.getByRole('button', { name: 'Start Voice Capture' });
    expect(startBtn.getAttribute('disabled')).not.toBeNull();
  });

  it('displays offline mock mode notice when isOffline is true', () => {
    render(
      <VoiceControls
        isRecording={false}
        recordingState="idle"
        isOffline={true}
        onToggleRecording={vi.fn()}
      />
    );

    expect(screen.getByText(/Offline Mock Mode/i)).toBeTruthy();
  });

  it('renders error alert banner with dismiss action', () => {
    const onDismiss = vi.fn();
    render(
      <VoiceControls
        isRecording={false}
        recordingState="idle"
        errorMessage="Microphone permission was denied."
        onDismissError={onDismiss}
        onToggleRecording={vi.fn()}
      />
    );

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('Microphone permission was denied.');

    const dismissBtn = screen.getByRole('button', { name: 'Dismiss error message' });
    fireEvent.click(dismissBtn);
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
