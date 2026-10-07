import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw/http';
import { describe, expect, it } from 'vitest';

import { getAccessToken, getRefreshToken } from '../../lib/auth';
import { REFRESH_STORAGE_KEY } from '../../lib/constants';
import { HR_EMAIL } from '../../test/handlers';
import { renderApp } from '../../test/render';
import { server } from '../../test/setup';

function countRefreshes(status = 200) {
  const calls = { count: 0 };
  server.use(
    http.post('/api/v1/auth/refresh/', () => {
      calls.count += 1;
      return status === 200
        ? HttpResponse.json({ access: 'access-2', refresh: 'refresh-2' })
        : HttpResponse.json({ detail: 'Token is blacklisted' }, { status });
    }),
  );
  return calls;
}

describe('SessionGate', () => {
  it('refreshes once on load when a refresh token is stored and lands signed in', async () => {
    localStorage.setItem(REFRESH_STORAGE_KEY, 'refresh-1');
    const refreshes = countRefreshes();

    renderApp('/employees', { gate: true });

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    await screen.findByRole('heading', { name: 'Employees' });
    await screen.findByText(HR_EMAIL);
    expect(refreshes.count).toBe(1);
    expect(getAccessToken()).toBe('access-2');
    expect(getRefreshToken()).toBe('refresh-2');
  });

  it('starts signed out without a stored token and never calls refresh', async () => {
    const refreshes = countRefreshes();

    renderApp('/employees', { gate: true });

    await screen.findByRole('heading', { name: 'ACME Salary' });
    expect(refreshes.count).toBe(0);
  });

  it('forgets a refused token and shows the login page', async () => {
    localStorage.setItem(REFRESH_STORAGE_KEY, 'refresh-stale');
    countRefreshes(401);

    renderApp('/employees', { gate: true });

    await screen.findByRole('heading', { name: 'ACME Salary' });
    expect(getRefreshToken()).toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it('keeps the token when the refresh fails for a reason other than a refusal', async () => {
    localStorage.setItem(REFRESH_STORAGE_KEY, 'refresh-1');
    countRefreshes(502);

    renderApp('/employees', { gate: true });

    await screen.findByRole('heading', { name: 'ACME Salary' });
    expect(getRefreshToken()).toBe('refresh-1');
    expect(getAccessToken()).toBeNull();
  });
});
