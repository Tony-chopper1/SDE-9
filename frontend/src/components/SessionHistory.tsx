import React from 'react';
import { RecordingSession } from '../types/speech';

export interface SessionHistoryProps {
  history: RecordingSession[];
  selectedSessionId: string | null;
  onSelectSession: (id: string | null) => void;
  onDeleteSession: (id: string) => void;
  onDownloadTranscript: (session: RecordingSession) => void;
}

export const SessionHistory: React.FC<SessionHistoryProps> = ({
  history,
  selectedSessionId,
  onSelectSession,
  onDeleteSession,
  onDownloadTranscript,
}) => {
  const handleDelete = (session: RecordingSession) => {
    const confirmed = window.confirm(
      `Are you sure you want to delete the recording session from ${session.date}?`
    );
    if (confirmed) {
      onDeleteSession(session.id);
    }
  };

  return (
    <section className="session-history-card" aria-label="Recording History">
      <div className="card-header">
        <div>
          <span className="section-eyebrow">SAVED SESSIONS</span>
          <h2 className="card-title">Recording History</h2>
        </div>

        <span
          className="history-count-badge"
          aria-label={`${history.length} saved recordings`}
        >
          {history.length} {history.length === 1 ? 'Session' : 'Sessions'}
        </span>
      </div>

      {history.length === 0 ? (
        <div className="history-empty" role="status">
          <p className="empty-text">No previous recordings found.</p>
          <p className="empty-subtext">Completed recordings will be automatically saved here.</p>
        </div>
      ) : (
        <div className="history-list" role="list">
          {history.map((session, index) => {
            const isSelected = selectedSessionId === session.id;
            const sessionNumber = history.length - index;

            return (
              <div
                key={session.id}
                className={`history-item-row ${isSelected ? 'is-selected' : ''}`}
                role="listitem"
              >
                <button
                  type="button"
                  className="history-select-btn"
                  onClick={() => onSelectSession(isSelected ? null : session.id)}
                  aria-pressed={isSelected}
                  aria-label={`Recording session #${sessionNumber} from ${session.date}. ${isSelected ? 'Currently selected' : 'Click to view'}`}
                >
                  <div className="history-item-header">
                    <span className="session-index-pill">Session #{sessionNumber}</span>
                    <time className="session-date">{session.date}</time>
                  </div>
                  <p className="session-preview">{session.transcript}</p>
                </button>

                <div className="history-item-actions">
                  <button
                    type="button"
                    className="history-action-btn download-btn"
                    onClick={() => onDownloadTranscript(session)}
                    aria-label={`Download transcript for session #${sessionNumber} recorded on ${session.date}`}
                    title="Download transcript as text file"
                  >
                    ↓ Download
                  </button>

                  <button
                    type="button"
                    className="history-action-btn delete-btn"
                    onClick={() => handleDelete(session)}
                    aria-label={`Delete session #${sessionNumber} recorded on ${session.date}`}
                    title="Delete recording session"
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selectedSessionId && (
        <div className="history-footer-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={() => onSelectSession(null)}
            aria-label="Return to live recording view"
          >
            ← Back to Live Session
          </button>
        </div>
      )}
    </section>
  );
};
