import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../components/ErrorBoundary';

const BombComponent: React.FC<{ shouldThrow?: boolean }> = ({ shouldThrow }) => {
  if (shouldThrow) {
    throw new Error('Explosive test failure');
  }
  return <div>Safe child content</div>;
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('ErrorBoundary Component', () => {
  it('renders children normally when no error occurs', () => {
    render(
      <ErrorBoundary>
        <BombComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Safe child content')).toBeTruthy();
  });

  it('catches thrown error and displays accessible fallback UI', () => {
    // Suppress console.error in test output for intended throw
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <BombComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    const alert = screen.getByRole('alert');
    expect(alert).toBeTruthy();
    expect(screen.getByText('Application Encountered an Error')).toBeTruthy();
    expect(screen.getByText('Explosive test failure')).toBeTruthy();

    const reloadBtn = screen.getByRole('button', { name: 'Reload Application' });
    expect(reloadBtn).toBeTruthy();

    const reloadSpy = vi.fn();
    Object.defineProperty(window, 'location', {
      writable: true,
      value: { reload: reloadSpy },
    });

    fireEvent.click(reloadBtn);
    expect(reloadSpy).toHaveBeenCalled();
  });
});
