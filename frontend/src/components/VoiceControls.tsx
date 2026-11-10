import React from 'react';
import { MicPermissionState } from '../types/speech';

export interface VoiceControlsProps {
  isRecording: boolean;
  onToggleRecording: () => void;
  errorMessage?: string;
  onDismissError?: () => void;
  micPermission?: MicPermissionState;
}

export const VoiceControls: React.FC<VoiceControlsProps> = ({
  isRecording,
  onToggleRecording,
  errorMessage,
  onDismissError,
  micPermission = 'prompt',
}) => {
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

          <div className="status-badge" role="status">
            <span
              className={`status-indicator-dot ${isRecording ? 'is-recording' : 'is-standby'}`}
              aria-hidden="true"
            />
            <span className="status-text">{isRecording ? 'RECORDING' : 'STANDBY'}</span>
          </div>
        </div>
      </div>

      <div className={`mic-stage ${isRecording ? 'is-recording' : ''}`}>
        <div className="mic-aura-ring ring-outer" aria-hidden="true" />
        <div className="mic-aura-ring ring-inner" aria-hidden="true" />

        <button
          type="button"
          className={`mic-action-button ${isRecording ? 'is-active' : ''}`}
          onClick={onToggleRecording}
          aria-label={isRecording ? 'Quick Stop Voice Recording' : 'Quick Start Voice Recording'}
          aria-pressed={isRecording}
        >
          <span className="mic-icon" aria-hidden="true">
            {isRecording ? '⏹' : '🎙'}
          </span>
        </button>
      </div>

      <div className="control-prompt">
        <h3 className="prompt-headline">
          {isRecording ? 'Listening to your voice...' : 'Ready to capture audio'}
        </h3>
        <p className="prompt-subtext">
          {isRecording
            ? 'Speak clearly into your microphone. Click below when finished.'
            : 'Press the capture button to begin speaking.'}
        </p>
      </div>

      {/* Audio Waveform Graphic */}
      <div
        className={`waveform-container ${isRecording ? 'is-active' : ''}`}
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

      <div className="action-button-row">
        <button
          type="button"
          className={`primary-record-btn ${isRecording ? 'is-recording' : ''}`}
          onClick={onToggleRecording}
          aria-pressed={isRecording}
          aria-label={isRecording ? 'Stop Recording' : 'Start Voice Capture'}
        >
          {isRecording ? 'Stop Recording' : 'Start Voice Capture'}
        </button>
      </div>

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
