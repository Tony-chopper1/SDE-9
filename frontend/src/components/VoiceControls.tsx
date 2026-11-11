import React from 'react';
import { RecordingState, MicPermissionState } from '../types/speech';

export interface VoiceControlsProps {
  isRecording: boolean;
  onToggleRecording: () => void;
  errorMessage?: string;
  onDismissError?: () => void;

  // Week 2 Extensions:
  recordingState?: RecordingState;
  isPaused?: boolean;
  isLoading?: boolean;
  isOffline?: boolean;
  onPause?: () => void;
  onResume?: () => void;
  onStop?: () => void;
  micPermission?: MicPermissionState;
}

export const VoiceControls: React.FC<VoiceControlsProps> = ({
  isRecording,
  onToggleRecording,
  errorMessage,
  onDismissError,
  recordingState,
  isPaused = false,
  isLoading = false,
  isOffline = false,
  onPause,
  onResume,
  onStop,
  micPermission = 'prompt',
}) => {
  // Determine effective state: explicit recordingState takes precedence; fallback to boolean props
  const effectiveState: RecordingState =
    recordingState ?? (isRecording ? (isPaused ? 'paused' : 'recording') : 'idle');

  const isCapturing = effectiveState === 'recording';
  const isSuspended = effectiveState === 'paused';
  const isIdle = effectiveState === 'idle';

  const displayStatus = isCapturing ? 'RECORDING' : isSuspended ? 'PAUSED' : 'STANDBY';

  return (
    <section className="voice-controls-card" aria-label="Voice Capture Controls">
      <div className="card-header">
        <div>
          <span className="section-eyebrow">VOICE CAPTURE</span>
          <h2 className="card-title">Recording Studio</h2>
        </div>

        <div className="card-header-badges">
          {/* Accessible Microphone Permission State Badge */}
          <div
            className={`permission-badge perm-${micPermission}`}
            role="status"
            aria-label={`Microphone permission: ${micPermission}`}
          >
            <span
              className={`perm-dot perm-dot-${micPermission}`}
              aria-hidden="true"
            />
            <span className="perm-label">MIC: {micPermission.toUpperCase()}</span>
          </div>

          <div className="status-badge" role="status" aria-label={`Current state: ${displayStatus}`}>
            <span
              className={`status-indicator-dot ${
                isCapturing ? 'is-recording' : isSuspended ? 'is-paused' : 'is-standby'
              }`}
              aria-hidden="true"
            />
            <span className="status-text">{displayStatus}</span>
          </div>
        </div>
      </div>

      {/* Offline Mode Banner */}
      {isOffline && (
        <div className="offline-mode-banner" role="status">
          <span className="offline-mode-icon" aria-hidden="true">⚡</span>
          <span className="offline-mode-text">
            Offline Mock Mode — speech is captured locally; backend sync is simulated.
          </span>
        </div>
      )}

      {/* Mic Stage with Aura Rings */}
      <div className={`mic-stage ${isCapturing ? 'is-recording' : isSuspended ? 'is-paused' : ''}`}>
        <div className="mic-aura-ring ring-outer" aria-hidden="true" />
        <div className="mic-aura-ring ring-inner" aria-hidden="true" />

        <button
          type="button"
          className={`mic-action-button ${isCapturing ? 'is-active' : isSuspended ? 'is-paused' : ''}`}
          onClick={isIdle ? onToggleRecording : (isCapturing ? onPause : onResume)}
          disabled={isLoading}
          aria-label={
            isIdle
              ? 'Quick Start Voice Recording'
              : isCapturing
              ? 'Quick Pause Voice Recording'
              : 'Quick Resume Voice Recording'
          }
          aria-pressed={isCapturing || isSuspended}
        >
          <span className="mic-icon" aria-hidden="true">
            {isLoading ? '⏳' : isCapturing ? '🎙' : isSuspended ? '⏸' : '🎙'}
          </span>
        </button>
      </div>

      {/* Dynamic Status Prompt */}
      <div className="control-prompt">
        <h3 className="prompt-headline">
          {isLoading
            ? 'Accessing microphone...'
            : isCapturing
            ? 'Listening to your voice...'
            : isSuspended
            ? 'Recording paused'
            : 'Ready to capture audio'}
        </h3>
        <p className="prompt-subtext">
          {isLoading
            ? 'Please grant microphone permission when prompted by your browser.'
            : isCapturing
            ? 'Speak clearly into your microphone. Pause or stop when finished.'
            : isSuspended
            ? 'Click Resume to continue speaking, or Stop to finish and save.'
            : 'Press the capture button or use Alt+R to begin speaking.'}
        </p>
      </div>

      {/* Audio Waveform Graphic */}
      <div
        className={`waveform-container ${isCapturing ? 'is-active' : isSuspended ? 'is-paused' : ''}`}
        aria-hidden="true"
      >
        {Array.from({ length: 32 }, (_, i) => (
          <span
            key={i}
            className="waveform-bar"
            style={{
              height: `${14 + ((i * 19 + 7) % 32)}px`,
              animationDelay: `${(i % 16) * 0.06}s`,
            }}
          />
        ))}
      </div>

      {/* Action Buttons Row */}
      <div className="action-button-row">
        {isIdle && (
          <button
            type="button"
            className="primary-record-btn"
            onClick={onToggleRecording}
            disabled={isLoading}
            aria-pressed={false}
            aria-label="Start Voice Capture"
          >
            {isLoading ? 'Initializing...' : 'Start Voice Capture'}
          </button>
        )}

        {isCapturing && (
          <div className="recording-controls-group">
            <button
              type="button"
              className="secondary-control-btn pause-action-btn"
              onClick={onPause}
              disabled={isLoading}
              aria-label="Pause Recording"
              title="Pause voice capture (Alt+P)"
            >
              <span aria-hidden="true">⏸</span> Pause
            </button>

            <button
              type="button"
              className="primary-record-btn is-recording stop-action-btn"
              onClick={onStop || onToggleRecording}
              disabled={isLoading}
              aria-pressed={true}
              aria-label="Stop Recording"
              title="Stop voice capture (Alt+R)"
            >
              <span aria-hidden="true">⏹</span> Stop Recording
            </button>
          </div>
        )}

        {isSuspended && (
          <div className="recording-controls-group">
            <button
              type="button"
              className="secondary-control-btn resume-action-btn"
              onClick={onResume}
              disabled={isLoading}
              aria-label="Resume Recording"
              title="Resume voice capture (Alt+P)"
            >
              <span aria-hidden="true">▶</span> Resume
            </button>

            <button
              type="button"
              className="primary-record-btn is-recording stop-action-btn"
              onClick={onStop || onToggleRecording}
              disabled={isLoading}
              aria-pressed={true}
              aria-label="Stop Recording"
              title="Stop and save recording (Alt+R)"
            >
              <span aria-hidden="true">⏹</span> Stop Recording
            </button>
          </div>
        )}
      </div>

      {/* Error Alert Banner */}
      {errorMessage && (
        <div
          className="error-alert-banner"
          role="alert"
          aria-live="assertive"
        >
          <span className="error-icon" aria-hidden="true">⚠️</span>
          <p className="error-text">{errorMessage}</p>
          {onDismissError && (
            <button
              type="button"
              className="error-dismiss-btn"
              onClick={onDismissError}
              aria-label="Dismiss error message"
            >
              ✕
            </button>
          )}
        </div>
      )}

      {/* Card Footer Meta */}
      <div className="card-footer-meta">
        <span className="meta-tag">
          <span className="meta-bullet" aria-hidden="true">●</span> Real-time transcription
        </span>
        <span className="meta-tag">
          <span className="meta-bullet" aria-hidden="true">●</span> WCAG 2.1 AA Compliant
        </span>
      </div>
    </section>
  );
};
