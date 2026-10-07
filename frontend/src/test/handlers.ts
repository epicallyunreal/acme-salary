import { http, HttpResponse } from 'msw/http';

import { employeePage } from './fixtures/employees';
import { countries, departments } from './fixtures/meta';

// One handler per API route the app calls. Each step adds its routes with realistic fixtures.
// Paths are relative, so MSW resolves them against the test page's origin.

export const HR_EMAIL = 'hr@acme.example';
export const HR_PASSWORD = 'correct-horse-battery';

function unauthorized(detail = 'Authentication credentials were not provided.') {
  return HttpResponse.json({ detail }, { status: 401 });
}

/** True when the request carries one of the access tokens the fixtures hand out. */
export function hasAccessToken(request: Request): boolean {
  return request.headers.get('authorization')?.startsWith('Bearer access-') ?? false;
}

export const authHandlers = [
  http.post('/api/v1/auth/login/', async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (body.email === HR_EMAIL && body.password === HR_PASSWORD) {
      return HttpResponse.json({ access: 'access-1', refresh: 'refresh-1' });
    }
    return unauthorized('No active account found with the given credentials');
  }),
  http.post('/api/v1/auth/refresh/', async ({ request }) => {
    const body = (await request.json()) as { refresh?: string };
    if (body.refresh?.startsWith('refresh-')) {
      return HttpResponse.json({ access: 'access-2', refresh: 'refresh-2' });
    }
    return HttpResponse.json(
      { detail: 'Token is invalid', code: 'token_not_valid' },
      { status: 401 },
    );
  }),
  http.post('/api/v1/auth/logout/', ({ request }) =>
    hasAccessToken(request) ? HttpResponse.json({}) : unauthorized(),
  ),
  http.get('/api/v1/auth/me/', ({ request }) =>
    hasAccessToken(request) ? HttpResponse.json({ id: 1, email: HR_EMAIL }) : unauthorized(),
  ),
];

/** Guarded like the real API: no bearer, no data. */
function authenticated(request: Request, body: Parameters<typeof HttpResponse.json>[0]) {
  return hasAccessToken(request) ? HttpResponse.json(body) : unauthorized();
}

export const metaHandlers = [
  http.get('/api/v1/meta/countries/', ({ request }) => authenticated(request, countries)),
  http.get('/api/v1/meta/departments/', ({ request }) => authenticated(request, departments)),
];

export const employeeHandlers = [
  http.get('/api/v1/employees/', ({ request }) => authenticated(request, employeePage)),
];

export const handlers = [
  http.get('/healthz', () => HttpResponse.json({ status: 'ok' })),
  ...authHandlers,
  ...metaHandlers,
  ...employeeHandlers,
];
