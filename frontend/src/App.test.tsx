import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import { reloadPage } from './lib/navigation';
import { PRELOAD_GUARD } from './lib/preloadRecovery';

vi.mock('./lib/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./lib/navigation')>()),
  reloadPage: vi.fn(),
}));

afterEach(() => {
  sessionStorage.clear();
  vi.mocked(reloadPage).mockClear();
});

describe('App', () => {
  it('starts signed out on the login page', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'ACME Salary' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });

  it('reloads once onto the new build when a chunk fails to load (D78)', () => {
    const first = new Event('vite:preloadError', { cancelable: true });
    const second = new Event('vite:preloadError', { cancelable: true });

    window.dispatchEvent(first);
    window.dispatchEvent(second);

    expect(first.defaultPrevented).toBe(true);
    expect(second.defaultPrevented).toBe(false);
    expect(reloadPage).toHaveBeenCalledTimes(1);
  });

  it('clears the reload guard once a navigation settles, so a later deploy reloads again', async () => {
    render(<App />);
    await screen.findByRole('heading', { name: 'ACME Salary' });
    sessionStorage.setItem(PRELOAD_GUARD, '1');

    act(() => {
      window.history.pushState({}, '', '/login?next=%2Fhelp');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    await waitFor(() => expect(sessionStorage.getItem(PRELOAD_GUARD)).toBeNull());
  });
});
