import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  refreshOnce,
  setSession,
} from '../lib/auth';
import { REFRESH_STORAGE_KEY } from '../lib/constants';
import { HR_EMAIL, HR_PASSWORD } from '../test/handlers';
import { server } from '../test/setup';
import { logout } from './auth';
import { ApiError, apiFetch, buildQuery, setUnauthenticatedHandler } from './client';
import type { Me } from './types';

describe('buildQuery', () => {
  it('joins arrays with commas and drops empty values', () => {
    expect(
      buildQuery({
        country: ['IN', 'US'],
        page: 2,
        search: '',
        on: undefined,
        level: null,
        flag: false,
      }),
    ).toBe('?country=IN%2CUS&page=2&flag=false');
    expect(buildQuery({ country: [] })).toBe('');
    expect(buildQuery(undefined)).toBe('');
  });
});

describe('apiFetch', () => {
  beforeEach(() => {
    setSession({ access: 'access-old', refresh: 'refresh-1' });
  });

  it('refreshes once for two concurrent 401s and retries both requests', async () => {
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh/', () => {
        refreshes += 1;
        return HttpResponse.json({ access: 'access-new', refresh: 'refresh-2' });
      }),
      http.get('/api/v1/auth/me/', ({ request }) =>
        request.headers.get('authorization') === 'Bearer access-new'
          ? HttpResponse.json({ id: 1, email: HR_EMAIL })
          : HttpResponse.json({ detail: 'expired' }, { status: 401 }),
      ),
    );

    const [first, second] = await Promise.all([
      apiFetch<Me>('/auth/me/'),
      apiFetch<Me>('/auth/me/'),
    ]);

    expect(first.email).toBe(HR_EMAIL);
    expect(second.email).toBe(HR_EMAIL);
    expect(refreshes).toBe(1);
    expect(getAccessToken()).toBe('access-new');
    expect(getRefreshToken()).toBe('refresh-2');
  });

  it('ends the session and calls the handler when the refresh is refused', async () => {
    const onUnauthenticated = vi.fn();
    setUnauthenticatedHandler(onUnauthenticated);
    server.use(
      http.post('/api/v1/auth/refresh/', () =>
        HttpResponse.json({ detail: 'Token is blacklisted' }, { status: 401 }),
      ),
      http.get('/api/v1/auth/me/', () => HttpResponse.json({ detail: 'expired' }, { status: 401 })),
    );

    await expect(apiFetch('/auth/me/')).rejects.toMatchObject({ status: 401 });

    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
  });

  it('keeps and uses a newer token when another tab rotated it first', async () => {
    const presented: string[] = [];
    server.use(
      http.post('/api/v1/auth/refresh/', async ({ request }) => {
        const body = (await request.json()) as { refresh: string };
        presented.push(body.refresh);
        if (body.refresh === 'refresh-1') {
          // The other tab's rotation landed in storage while this request was in flight.
          localStorage.setItem(REFRESH_STORAGE_KEY, 'refresh-2');
          return HttpResponse.json({ detail: 'Token is blacklisted' }, { status: 401 });
        }
        return HttpResponse.json({ access: 'access-new', refresh: 'refresh-3' });
      }),
      http.get('/api/v1/auth/me/', ({ request }) =>
        request.headers.get('authorization') === 'Bearer access-new'
          ? HttpResponse.json({ id: 1, email: HR_EMAIL })
          : HttpResponse.json({ detail: 'expired' }, { status: 401 }),
      ),
    );

    const me = await apiFetch<Me>('/auth/me/');

    expect(me.email).toBe(HR_EMAIL);
    expect(presented).toEqual(['refresh-1', 'refresh-2']);
    expect(getRefreshToken()).toBe('refresh-3');
  });

  it('reads the stored token inside the cross-tab lock', async () => {
    const presented: string[] = [];
    const locks = {
      request: async (_name: string, callback: () => Promise<boolean>) => {
        // Another tab held the lock first and rotated the token before this tab's turn.
        localStorage.setItem(REFRESH_STORAGE_KEY, 'refresh-2');
        return callback();
      },
    };
    Object.defineProperty(navigator, 'locks', { value: locks, configurable: true });
    server.use(
      http.post('/api/v1/auth/refresh/', async ({ request }) => {
        presented.push(((await request.json()) as { refresh: string }).refresh);
        return HttpResponse.json({ access: 'access-new', refresh: 'refresh-3' });
      }),
    );

    try {
      expect(await refreshOnce()).toBe(true);
    } finally {
      Object.defineProperty(navigator, 'locks', { value: undefined, configurable: true });
    }

    expect(presented).toEqual(['refresh-2']);
    expect(getAccessToken()).toBe('access-new');
  });

  it('ends the session when the retry after a good refresh still answers 401', async () => {
    const onUnauthenticated = vi.fn();
    setUnauthenticatedHandler(onUnauthenticated);
    server.use(
      http.get('/api/v1/auth/me/', () => HttpResponse.json({ detail: 'no' }, { status: 401 })),
    );

    await expect(apiFetch('/auth/me/')).rejects.toMatchObject({ status: 401 });

    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });

  it('does not refresh when there is no session, so login errors come straight back', async () => {
    clearSession();
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh/', () => {
        refreshes += 1;
        return HttpResponse.json({}, { status: 401 });
      }),
    );

    const error = await apiFetch('/auth/login/', {
      method: 'POST',
      body: { email: HR_EMAIL, password: 'wrong' },
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).detail()).toBe('No active account found with the given credentials');
    expect(refreshes).toBe(0);
  });

  it('signs out with the rotated refresh token when the access token had expired', async () => {
    let refreshes = 0;
    const blacklisted: string[] = [];
    server.use(
      http.post('/api/v1/auth/refresh/', () => {
        refreshes += 1;
        return HttpResponse.json({ access: 'access-new', refresh: 'refresh-2' });
      }),
      http.post('/api/v1/auth/logout/', async ({ request }) => {
        if (request.headers.get('authorization') !== 'Bearer access-new') {
          return HttpResponse.json({ detail: 'expired' }, { status: 401 });
        }
        const body = (await request.json()) as { refresh: string };
        blacklisted.push(body.refresh);
        return HttpResponse.json({});
      }),
    );

    await logout();

    expect(refreshes).toBe(1);
    expect(blacklisted).toEqual(['refresh-2']);
  });

  it('exposes DRF field errors on a 400', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json(
          { currency: ['currency=local needs exactly one country in the filter'] },
          { status: 400 },
        ),
      ),
    );

    const error = (await apiFetch('/employees/').catch((caught: unknown) => caught)) as ApiError;

    expect(error.status).toBe(400);
    expect(error.fieldErrors()).toEqual({
      currency: ['currency=local needs exactly one country in the filter'],
    });
    expect(error.detail()).toBeNull();
  });

  it('returns both tokens on a good login', async () => {
    clearSession();
    const tokens = await apiFetch<{ access: string; refresh: string }>('/auth/login/', {
      method: 'POST',
      body: { email: HR_EMAIL, password: HR_PASSWORD },
    });

    expect(tokens).toEqual({ access: 'access-1', refresh: 'refresh-1' });
  });
});
