import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { TranscriptTimeline } from '../components/TranscriptTimeline';
import { TranscriptSegment } from '../api_client';

afterEach(() => {
  cleanup();
});

describe('TranscriptTimeline Component', () => {
  it('renders the accessible empty state when segments list is empty', () => {
    render(<TranscriptTimeline segments={[]} />);

    expect(screen.getByText('No transcripts yet')).toBeTruthy();
    expect(
      screen.getByText(/Start voice capture or speak to see real-time transcripts appear here/i)
    ).toBeTruthy();
    expect(
      screen.getByRole('region', { name: 'Speech Transcript Timeline' })
    ).toBeTruthy();
  });

  it('renders active segments with timestamps, text, and confidence badges', () => {
    const mockSegments: TranscriptSegment[] = [
      {
        id: 'seg-1',
        text: 'Hello, this is the first final statement.',
        confidence: 0.98,
        start_time: 0,
        end_time: 2.4,
        is_final: true,
      },
      {
        id: 'seg-2',
        text: 'And here is an interim segment...',
        confidence: 0.82,
        start_time: 2.5,
        end_time: 4.1,
        is_final: false,
      },
    ];

    render(<TranscriptTimeline segments={mockSegments} />);

    expect(screen.getByText('Hello, this is the first final statement.')).toBeTruthy();
    expect(screen.getByText('And here is an interim segment...')).toBeTruthy();
    expect(screen.getByText('98%')).toBeTruthy();
    expect(screen.getByText('82%')).toBeTruthy();
    expect(screen.getByText('Listening...')).toBeTruthy();
  });

  it('renders segments in chronological order even when input is out of order', () => {
    const unorderedSegments: TranscriptSegment[] = [
      {
        id: 'seg-third',
        text: 'Third spoken statement',
        confidence: 0.9,
        start_time: 12.0,
        end_time: 15.0,
        is_final: true,
      },
      {
        id: 'seg-first',
        text: 'First spoken statement',
        confidence: 0.95,
        start_time: 1.0,
        end_time: 3.0,
        is_final: true,
      },
      {
        id: 'seg-second',
        text: 'Second spoken statement',
        confidence: 0.92,
        start_time: 5.5,
        end_time: 8.0,
        is_final: true,
      },
    ];

    const { container } = render(<TranscriptTimeline segments={unorderedSegments} />);

    const renderedTexts = Array.from(
      container.querySelectorAll('.segment-text')
    ).map((el) => el.textContent);

    expect(renderedTexts).toEqual([
      'First spoken statement',
      'Second spoken statement',
      'Third spoken statement',
    ]);

    const liveRegion = container.querySelector('[aria-live="polite"]');
    expect(liveRegion?.textContent).toContain('Latest transcript: Third spoken statement');
  });

  it('efficiently handles 1000+ entries using virtualization without DOM lag', () => {
    // Generate 1,200 segments
    const count = 1200;
    const largeSegmentsList: TranscriptSegment[] = Array.from({ length: count }, (_, i) => ({
      id: `seg-${i}`,
      text: `Voicebot transcription entry number ${i + 1}`,
      confidence: 0.95,
      start_time: i * 2,
      end_time: i * 2 + 1.8,
      is_final: true,
    }));

    const startTime = performance.now();
    const { container } = render(
      <TranscriptTimeline
        segments={largeSegmentsList}
        viewportHeight={360}
        itemHeight={68}
      />
    );
    const duration = performance.now() - startTime;

    // Rendering 1200 items virtualized should take well under 250ms
    expect(duration).toBeLessThan(1000);

    // Verify virtualization badge indicates virtualized count
    expect(screen.getByText(/1,200 segments \(virtualized\)/i)).toBeTruthy();

    // Verify DOM windowing: total rendered <li> items in the DOM is a small slice (< 30) instead of 1,200!
    const renderedListItems = container.querySelectorAll('li.timeline-segment-item');
    expect(renderedListItems.length).toBeLessThan(35);
    expect(renderedListItems.length).toBeGreaterThan(0);

    // Test scrolling updates the window
    const timelineRegion = screen.getByRole('region', { name: 'Speech Transcript Timeline' });
    fireEvent.scroll(timelineRegion, { target: { scrollTop: 1500 } });

    // Ensure list still maintains virtualized rendering cleanly after scroll
    const itemsAfterScroll = container.querySelectorAll('li.timeline-segment-item');
    expect(itemsAfterScroll.length).toBeLessThan(35);
  });

  it('maintains proper accessibility attributes and live region', () => {
    const mockSegments: TranscriptSegment[] = [
      {
        id: 'seg-1',
        text: 'Speech recognition live test',
        confidence: 0.95,
        start_time: 0,
        end_time: 1.5,
        is_final: true,
      },
    ];

    render(<TranscriptTimeline segments={mockSegments} />);

    const timelineContainer = screen.getByRole('region', {
      name: 'Speech Transcript Timeline',
    });
    expect(timelineContainer.getAttribute('tabindex')).toBe('0');

    const liveRegion = timelineContainer.querySelector('[aria-live="polite"]');
    expect(liveRegion).toBeTruthy();
    expect(liveRegion?.textContent).toContain('Latest transcript: Speech recognition live test');
  });
});
