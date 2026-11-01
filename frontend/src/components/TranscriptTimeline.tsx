
import React from 'react';
import { TranscriptSegment } from '../api_client';

export interface TranscriptTimelineProps {
  segments: TranscriptSegment[];
}

export const TranscriptTimeline: React.FC<TranscriptTimelineProps> = ({
  segments,
}) => {
  return (
    <section
      className="timeline"
      aria-label="Speech Transcript Timeline"
      tabIndex={0}
    >
      {segments.length === 0 ? (
        <p className="empty-transcript">
          Your transcript will appear here once you start speaking...
        </p>
      ) : (
        <ul>
          {segments.map((seg) => (
            <li key={seg.id}>
              <span className="segment-time">
                [{Math.floor(seg.start_time)}s - {Math.floor(seg.end_time)}s]
              </span>
              <p>{seg.text}</p>
              {!seg.is_final && (
                <span className="interim-label">Listening...</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};
