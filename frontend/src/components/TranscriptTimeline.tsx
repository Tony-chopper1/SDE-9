import React, { useState, useRef, useMemo, useEffect } from 'react';
import { TranscriptSegment } from '../api_client';

export interface TranscriptTimelineProps {
  segments: TranscriptSegment[];
  itemHeight?: number;
  viewportHeight?: number;
}

const DEFAULT_ITEM_HEIGHT = 68;
const DEFAULT_VIEWPORT_HEIGHT = 360;
const OVERSCAN_COUNT = 4;

export const TranscriptTimeline: React.FC<TranscriptTimelineProps> = ({
  segments,
  itemHeight = DEFAULT_ITEM_HEIGHT,
  viewportHeight = DEFAULT_VIEWPORT_HEIGHT,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // Ensure segments are always ordered chronologically by ascending start_time
  const sortedSegments = useMemo(() => {
    return [...segments].sort((a, b) => a.start_time - b.start_time);
  }, [segments]);

  // Virtualization window calculations
  const totalCount = sortedSegments.length;
  const isVirtualized = totalCount > 25;

  const { startIndex, endIndex, offsetY, totalHeight } = useMemo(() => {
    if (!isVirtualized) {
      return {
        startIndex: 0,
        endIndex: totalCount,
        offsetY: 0,
        totalHeight: totalCount * itemHeight,
      };
    }

    const start = Math.max(0, Math.floor(scrollTop / itemHeight) - OVERSCAN_COUNT);
    const visibleCapacity = Math.ceil(viewportHeight / itemHeight) + 2 * OVERSCAN_COUNT;
    const end = Math.min(totalCount, start + visibleCapacity);
    const topOffset = start * itemHeight;

    return {
      startIndex: start,
      endIndex: end,
      offsetY: topOffset,
      totalHeight: totalCount * itemHeight,
    };
  }, [totalCount, isVirtualized, scrollTop, itemHeight, viewportHeight]);

  const visibleSegments = useMemo(() => {
    return sortedSegments.slice(startIndex, endIndex);
  }, [sortedSegments, startIndex, endIndex]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  };

  // Auto-scroll to latest segment on new incoming items if user is near bottom
  const prevCountRef = useRef(totalCount);
  useEffect(() => {
    if (totalCount > prevCountRef.current && containerRef.current) {
      const container = containerRef.current;
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
      if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
      }
    }
    prevCountRef.current = totalCount;
  }, [totalCount]);

  if (totalCount === 0) {
    return (
      <section
        className="transcript-timeline empty-state"
        aria-label="Speech Transcript Timeline"
        tabIndex={0}
      >
        <div className="empty-message" role="status">
          <span className="empty-icon" aria-hidden="true">💬</span>
          <p className="empty-title">No transcripts yet</p>
          <p className="empty-subtitle">Start voice capture or speak to see real-time transcripts appear here.</p>
        </div>
      </section>
    );
  }

  return (
    <section
      ref={containerRef}
      className="transcript-timeline"
      aria-label="Speech Transcript Timeline"
      tabIndex={0}
      onScroll={handleScroll}
      style={{
        maxHeight: `${viewportHeight}px`,
        overflowY: 'auto',
        position: 'relative',
      }}
    >
      <div className="timeline-header-meta">
        <span className="segment-count-badge" aria-label={`Total segments: ${totalCount}`}>
          {totalCount.toLocaleString()} {totalCount === 1 ? 'segment' : 'segments'}
          {isVirtualized && ' (virtualized)'}
        </span>
      </div>

      {/* Screen reader live announcements */}
      <div aria-live="polite" aria-atomic="false" className="sr-only">
        {totalCount > 0 ? `Latest transcript: ${sortedSegments[totalCount - 1].text}` : ''}
      </div>

      <div
        className="timeline-virtual-container"
        style={{
          height: isVirtualized ? `${totalHeight}px` : 'auto',
          position: 'relative',
          width: '100%',
        }}
      >
        <ol
          className="timeline-list"
          role="list"
          style={{
            margin: 0,
            padding: 0,
            listStyle: 'none',
            transform: isVirtualized ? `translateY(${offsetY}px)` : 'none',
            position: isVirtualized ? 'absolute' : 'relative',
            top: 0,
            left: 0,
            right: 0,
          }}
        >
          {visibleSegments.map((seg, idx) => {
            const actualIndex = startIndex + idx;
            const startSec = Math.floor(seg.start_time);
            const endSec = Math.ceil(seg.end_time);
            const confidencePercent = Math.round(seg.confidence * 100);

            return (
              <li
                key={seg.id || `seg-${actualIndex}`}
                className={`timeline-segment-item ${seg.is_final ? 'is-final' : 'is-interim'}`}
                style={{
                  minHeight: `${itemHeight - 12}px`,
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '12px',
                  padding: '10px 14px',
                  borderBottom: '1px solid #e2e8f0',
                  backgroundColor: seg.is_final ? '#ffffff' : '#f8fafc',
                  transition: 'background-color 0.15s ease',
                }}
              >
                <div className="segment-meta" style={{ flexShrink: 0 }}>
                  <span
                    className="time-badge"
                    aria-label={`Timestamp from ${startSec} to ${endSec} seconds`}
                  >
                    {startSec}s - {endSec}s
                  </span>
                  {seg.confidence > 0 && (
                    <span
                      className="confidence-badge"
                      title={`${confidencePercent}% recognition confidence`}
                    >
                      {confidencePercent}%
                    </span>
                  )}
                </div>

                <div className="segment-content" style={{ flexGrow: 1, minWidth: 0 }}>
                  <p className="segment-text">{seg.text}</p>
                  {!seg.is_final && (
                    <span className="interim-tag" aria-label="Interim listening state">
                      Listening...
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
};
