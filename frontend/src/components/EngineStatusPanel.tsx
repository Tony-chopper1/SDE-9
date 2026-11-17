import React from 'react';

export interface EngineStatusData {
  engineName: string | null;
  latencyMs: number | null;
  speechApiStatus: 'online' | 'offline' | 'unknown';
  speechApiLabel?: string | null;
  backendStatus: 'online' | 'offline' | 'checking' | 'unknown';
}

export interface EngineStatusPanelProps {
  status?: Partial<EngineStatusData>;
}

export const EngineStatusPanel: React.FC<EngineStatusPanelProps> = ({ status }) => {
  const engineName = status?.engineName ?? null;
  const latencyMs = status?.latencyMs ?? null;
  const speechApiStatus = status?.speechApiStatus ?? 'unknown';
  const speechApiLabel = status?.speechApiLabel ?? null;
  const backendStatus = status?.backendStatus ?? 'unknown';

  // Determine Engine display & indicator
  const displayEngine = engineName || 'Not reported';
  let engineDotClass = 'dot-neutral';
  if (backendStatus === 'online' && engineName) {
    engineDotClass = 'dot-green';
  } else if (backendStatus === 'offline') {
    engineDotClass = 'dot-red';
  }

  // Determine Latency display & indicator
  const displayLatency = latencyMs !== null && latencyMs !== undefined ? `${latencyMs} ms` : '—';
  let latencyDotClass = 'dot-neutral';
  if (latencyMs !== null && latencyMs !== undefined && backendStatus === 'online') {
    latencyDotClass = 'dot-green';
  } else if (backendStatus === 'offline') {
    latencyDotClass = 'dot-red';
  }

  // Determine Speech API display & indicator
  let displaySpeechApi = 'Not reported';
  let speechDotClass = 'dot-neutral';
  if (speechApiStatus === 'online') {
    displaySpeechApi = speechApiLabel || 'Connected';
    speechDotClass = 'dot-green';
  } else if (speechApiStatus === 'offline') {
    displaySpeechApi = speechApiLabel || 'Offline';
    speechDotClass = 'dot-red';
  } else if (speechApiLabel && speechApiLabel !== 'Not reported') {
    displaySpeechApi = speechApiLabel;
  }

  return (
    <section
      className="engine-status-card"
      aria-labelledby="engine-status-heading"
      role="region"
    >
      <div className="engine-status-header">
        <h3 className="engine-status-label" id="engine-status-heading">
          ENGINE STATUS
        </h3>
      </div>

      <dl className="engine-status-list">
        {/* 1. Engine Name */}
        <div className="engine-status-row">
          <dt className="engine-status-key">Engine</dt>
          <dd className="engine-status-val">
            <span
              className={`engine-status-dot ${engineDotClass}`}
              aria-hidden="true"
            />
            <span aria-label={`Engine: ${displayEngine}`}>{displayEngine}</span>
          </dd>
        </div>

        {/* 2. Latency */}
        <div className="engine-status-row">
          <dt className="engine-status-key">Latency</dt>
          <dd className="engine-status-val">
            <span
              className={`engine-status-dot ${latencyDotClass}`}
              aria-hidden="true"
            />
            <span aria-label={`Latency: ${displayLatency}`}>{displayLatency}</span>
          </dd>
        </div>

        {/* 3. Speech API */}
        <div className="engine-status-row">
          <dt className="engine-status-key">Speech API</dt>
          <dd className="engine-status-val">
            <span
              className={`engine-status-dot ${speechDotClass}`}
              aria-hidden="true"
            />
            <span aria-label={`Speech API: ${displaySpeechApi}`}>{displaySpeechApi}</span>
          </dd>
        </div>
      </dl>
    </section>
  );
};
