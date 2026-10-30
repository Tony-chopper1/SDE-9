import React from 'react';
import { TranscriptSegment } from '../api_client';

export interface TranscriptTimelineProps {
  segments: TranscriptSegment[];
}

export const TranscriptTimeline: React.FC<TranscriptTimelineProps> = ({ segments }) => {
  return (
    <section aria-label="Speech Transcript Timeline" tabIndex={0} style={{ maxHeight: '350px', overflowY: 'auto' }}>
      {segments.length === 0 ? (
        <p style={{ color: '#777' }}>No spoken segments detected yet.</p>
      ) : (
        <ul style={{ listStyleType: 'none', padding: 0 }}>
          {segments.map((seg) => (
            <li
              key={seg.id}
              style={{
                padding: '8px',
                borderBottom: '1px solid #e0e0e0',
                backgroundColor: seg.is_final ? '#fff' : '#f9f9f9',
              }}
            >
              <span style={{ fontSize: '11px', color: '#666' }}>
                [{Math.floor(seg.start_time)}s - {Math.floor(seg.end_time)}s]
              </span>{' '}
              <strong>{seg.text}</strong>
              {!seg.is_final && <em style={{ fontSize: '11px', color: '#888' }}> (interim)</em>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
