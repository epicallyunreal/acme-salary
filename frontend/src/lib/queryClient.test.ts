import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { ApiError, apiFetch } from '../api/client';
import { server } from '../test/setup';
import { getAccessToken, setSession } from './auth';
import { createQueryClient, retryOnce } from './queryClient';

describe('retryOnce', () => {
  it.each([400, 401, 403, 404, 409, 413, 429])(
    'never retries a %i, since the answer would not change',
    (status) => {
      expect(retryOnce(0, new ApiError(status, {}))).toBe(false);
    },
  );

  it.each([500, 502, 503])('retries a %i once', (status) => {
    expect(retryOnce(0, new ApiError(status, {}))).toBe(true);
    expect(retryOnce(1, new ApiError(status, {}))).toBe(false);
  });

  it('retries a request that got no answer once', () => {
    const lost = new TypeError('Failed to fetch');

    expect(retryOnce(0, lost)).toBe(true);
    expect(retryOnce(1, lost)).toBe(false);
  });
});

describe("the app's query client", () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  /** Fetches `/things/` with the app's defaults, the retry delay aside, and counts the requests
   * the API saw. */
  async function fetchThings(answer: (request: Request) => Response) {
    const seen = { requests: 0 };
    server.use(
      http.get('/api/v1/things/', ({ request }) => {
        seen.requests += 1;
        return answer(request);
      }),
    );
    const result = createQueryClient()
      .fetchQuery({ queryKey: ['things'], queryFn: () => apiFetch('/things/'), retryDelay: 0 })
      .then(
        (data) => ({ data, error: null }),
        (error: unknown) => ({ data: null, error }),
      );
    return { ...(await result), seen };
  }

  it('asks once for a filter the API refuses', async () => {
    const { error, seen } = await fetchThings(() =>
      HttpResponse.json({ country: ['Unknown country_code: XX'] }, { status: 400 }),
    );

    expect(error).toMatchObject({ status: 400 });
    expect(seen.requests).toBe(1);
  });

  it('asks twice when the server fails and when no answer comes', async () => {
    const failed = await fetchThings(() => HttpResponse.json({}, { status: 500 }));
    const lost = await fetchThings(() => HttpResponse.error());

    expect(failed.error).toMatchObject({ status: 500 });
    expect(failed.seen.requests).toBe(2);
    expect(lost.error).toBeInstanceOf(TypeError);
    expect(lost.seen.requests).toBe(2);
  });

  it("still lets the client's own refresh answer the first 401", async () => {
    let refreshes = 0;
    server.use(
      http.post('/api/v1/auth/refresh/', () => {
        refreshes += 1;
        return HttpResponse.json({ access: 'access-2', refresh: 'refresh-2' });
      }),
    );

    const { data, seen } = await fetchThings((request) =>
      request.headers.get('authorization') === 'Bearer access-2'
        ? HttpResponse.json({ things: 3 })
        : HttpResponse.json({ detail: 'expired' }, { status: 401 }),
    );

    expect(data).toEqual({ things: 3 });
    expect(refreshes).toBe(1);
    expect(seen.requests).toBe(2);
    expect(getAccessToken()).toBe('access-2');
  });
});
