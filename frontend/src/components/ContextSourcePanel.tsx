import React, { useState, useCallback } from 'react';
import { TypedVoicebotClient, WindowContextData } from '../api_client';

export interface ContextSourcePanelProps {
  sessionId?: string;
  isScreenContextEnabled: boolean;
  onToggleScreenContext: (enabled: boolean) => void;
  client?: TypedVoicebotClient;
  isOffline?: boolean;
}

export const DEFAULT_MOCK_CONTEXT: WindowContextData = {
  app_name: 'Visual Studio Code',
  window_title: 'app.py — SDK-9 Voicebot (Mock Context)',
  app_type: 'ide',
  visible_snippet: 'def handle_voice_query(query: str):\n    # Context-aware voicebot processing\n    return reason_about_task(query)',
};

export const ContextSourcePanel: React.FC<ContextSourcePanelProps> = ({
  sessionId = 'demo-session',
  isScreenContextEnabled,
  onToggleScreenContext,
  client = new TypedVoicebotClient(),
  isOffline = false,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [syncMessage, setSyncMessage] = useState<string>('');
  const [isMockSync, setIsMockSync] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);

  const handleTestContextSync = useCallback(async () => {
    if (!isScreenContextEnabled) return;

    setIsSubmitting(true);
    setSyncStatus('idle');
    setSyncMessage('');
    setIsMockSync(false);

    try {
      const response = await client.submitContext({
        session_id: sessionId,
        application: DEFAULT_MOCK_CONTEXT.app_name,
        window_title: DEFAULT_MOCK_CONTEXT.window_title,
        active_window: DEFAULT_MOCK_CONTEXT,
        user_query: 'Current screen query simulation',
      });

      if (response.success) {
        setSyncStatus('success');
        setIsMockSync(false);
        setSyncMessage(`Backend Connected: Context accepted by server (ID: ${response.data?.context_id})`);
        setLastSyncTime(new Date().toLocaleTimeString());
      } else {
        setSyncStatus('error');
        setIsMockSync(false);
        setSyncMessage(response.error?.message || 'Context submission rejected by server');
      }
    } catch (err: unknown) {
      // Check if this error is due to backend unavailability (network error, failed to fetch, offline)
      const isNetworkUnreachable =
        isOffline ||
        err instanceof TypeError ||
        (err instanceof Error &&
          (err.message.toLowerCase().includes('failed to fetch') ||
           err.message.toLowerCase().includes('network') ||
           err.message.toLowerCase().includes('connection') ||
           err.message.toLowerCase().includes('econnrefused') ||
           err.message.toLowerCase().includes('fetch failed')));

      if (isNetworkUnreachable) {
        // Backend unavailable: Provide clearly labelled mock/demo response
        setSyncStatus('success');
        setIsMockSync(true);
        setSyncMessage(
          `Mock Demo Mode: Context processed locally (Backend server offline). Simulated sync accepted for ${DEFAULT_MOCK_CONTEXT.app_name}.`
        );
        setLastSyncTime(new Date().toLocaleTimeString());
      } else {
        // Actual server API error (e.g. HTTP 400, 500 from responding server)
        setSyncStatus('error');
        setIsMockSync(false);
        const msg = err instanceof Error ? err.message : 'Context sync failed with server error';
        setSyncMessage(msg);
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [client, isOffline, isScreenContextEnabled, sessionId]);

  return (
    <section className="context-source-panel-card" aria-label="Context & Source Panel">
      <div className="card-header">
        <div>
          <span className="section-eyebrow">MULTIMODAL CONTEXT</span>
          <h2 className="card-title">Context & Sources</h2>
        </div>

        {/* Explicit Screen-Context Switch Toggle (Strictly defaults to OFF) */}
        <div className="context-toggle-wrapper">
          <label htmlFor="screen-context-toggle" className="toggle-label">
            Screen Context
          </label>
          <button
            id="screen-context-toggle"
            type="button"
            role="switch"
            aria-checked={isScreenContextEnabled}
            className={`context-switch-btn ${isScreenContextEnabled ? 'is-enabled' : 'is-disabled'}`}
            onClick={() => onToggleScreenContext(!isScreenContextEnabled)}
            aria-label={`Toggle Screen Context (currently ${isScreenContextEnabled ? 'ON' : 'OFF'}, shortcut Alt+C)`}
            title="Toggle Screen Context (Alt+C)"
          >
            <span className="switch-slider" aria-hidden="true" />
            <span className="switch-text">{isScreenContextEnabled ? 'ON' : 'OFF'}</span>
          </button>
        </div>
      </div>

      {/* When OFF: Privacy protected notice */}
      {!isScreenContextEnabled ? (
        <div className="context-off-banner" role="status">
          <div className="context-shield-icon" aria-hidden="true">🛡️</div>
          <div className="context-off-details">
            <h3 className="context-off-title">Screen context is disabled. Only spoken audio input is captured.</h3>
            <p className="context-off-description">
              Privacy First: No screen contents, window metadata, or OCR text will be collected or processed by the AI engine. You may enable context above if you wish to simulate contextual workspace assistance.
            </p>
          </div>
        </div>
      ) : (
        /* When ON: Clearly labelled mock context/source information */
        <div className="context-active-view">
          <div className="context-mock-notice" role="note">
            <span className="mock-badge" aria-hidden="true">MOCK DEMO</span>
            <p className="mock-notice-text">
              Demonstration mode: Simulated application context is active. No actual screen capture or personal data is recorded.
            </p>
          </div>

          <div className="context-metadata-grid">
            <div className="context-meta-row">
              <span className="context-key">Active Application:</span>
              <span className="context-val">{DEFAULT_MOCK_CONTEXT.app_name}</span>
            </div>
            <div className="context-meta-row">
              <span className="context-key">Window Title:</span>
              <span className="context-val">{DEFAULT_MOCK_CONTEXT.window_title}</span>
            </div>
            <div className="context-meta-row">
              <span className="context-key">Application Type:</span>
              <span className="context-val">{DEFAULT_MOCK_CONTEXT.app_type?.toUpperCase()}</span>
            </div>
          </div>

          <div className="context-snippet-box">
            <span className="snippet-label">Simulated Editor Snippet:</span>
            <pre className="snippet-code" tabIndex={0} aria-label="Visible code snippet">
              <code>{DEFAULT_MOCK_CONTEXT.visible_snippet}</code>
            </pre>
          </div>

          {/* Contributing Context Sources */}
          <div className="context-sources-list" aria-label="Context Sources">
            <span className="sources-heading">Contributing Sources:</span>
            <div className="sources-tags-row">
              <span className="source-tag">🎙️ Audio VAD Engine</span>
              <span className="source-tag">💻 Mock Window Sensor</span>
              <span className="source-tag">💬 Session History Turns</span>
            </div>
          </div>

          {/* Manual Refresh / Test Context Action */}
          <div className="context-actions-row">
            <button
              type="button"
              className="context-sync-btn"
              onClick={handleTestContextSync}
              disabled={isSubmitting}
              aria-label="Test Context Sync with API"
              title="Send mock context payload to verified API endpoint"
            >
              {isSubmitting ? 'Syncing Context...' : '⚡ Test Context Sync'}
            </button>

            {lastSyncTime && (
              <span className="last-sync-time">Last synced: {lastSyncTime}</span>
            )}
          </div>

          {/* Sync Status Feedback */}
          {syncStatus === 'success' && (
            <div
              className={`sync-feedback ${isMockSync ? 'mock-demo' : 'success'}`}
              role="status"
              aria-live="polite"
            >
              <span className="feedback-badge" aria-hidden="true">
                {isMockSync ? 'MOCK DEMO' : 'LIVE'}
              </span>
              <span className="feedback-text">{syncMessage}</span>
            </div>
          )}

          {syncStatus === 'error' && (
            <div className="sync-feedback error" role="alert" aria-live="assertive">
              <span aria-hidden="true">⚠️</span>
              <span className="feedback-text">{syncMessage}</span>
            </div>
          )}
        </div>
      )}

      <div className="card-footer-meta">
        <span className="meta-tag">
          <span className="meta-bullet" aria-hidden="true">●</span> Privacy opt-in model
        </span>
        <span className="meta-tag">
          <span className="meta-bullet" aria-hidden="true">●</span> Keyboard Shortcut: Alt+C
        </span>
      </div>
    </section>
  );
};
