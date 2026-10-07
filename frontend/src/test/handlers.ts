import { http, HttpResponse } from 'msw/http';

import { auditPage, employeeDetails, histories } from './fixtures/detail';
import { employeePage } from './fixtures/employees';
import { batches, batchPage, reviewBatch, reviewRows, rowsPage } from './fixtures/imports';
import { exchangeRates, insightFor } from './fixtures/insights';
import { componentsFor, countries, departments } from './fixtures/meta';

// One handler per API route the app calls. Each step adds its routes with realistic fixtures.
// Paths are relative, so MSW resolves them against the test page's origin.

export const HR_EMAIL = 'hr@acme.example';
export const HR_PASSWORD = 'correct-horse-battery';

function unauthorized(detail = 'Authentication credentials were not provided.') {
  return HttpResponse.json({ detail }, { status: 401 });
}

function notFound(model: string) {
  return HttpResponse.json({ detail: `No ${model} matches the given query.` }, { status: 404 });
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
  http.get('/api/v1/meta/exchange-rates/', ({ request }) => authenticated(request, exchangeRates)),
  http.get('/api/v1/meta/components/', ({ request }) =>
    authenticated(request, componentsFor(new URL(request.url).searchParams.get('country') ?? '')),
  ),
];

export const employeeHandlers = [
  http.get('/api/v1/employees/', ({ request }) => authenticated(request, employeePage)),
  http.post('/api/v1/employees/', async ({ request }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const body = (await request.json()) as { full_name: string; email: string };
    return HttpResponse.json(
      {
        ...employeeDetails[1],
        id: 5,
        employee_code: 'ACME-5',
        legacy_code: null,
        full_name: body.full_name,
        email: body.email.toLowerCase(),
        warnings: [],
      },
      { status: 201 },
    );
  }),
  http.patch('/api/v1/employees/:id/', async ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const employee = employeeDetails[Number(params.id)];
    if (!employee) return notFound('Employee');
    const patch = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...employee, ...patch, department: employee.department });
  }),
  http.post('/api/v1/employees/:id/compensation/', async ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const records = histories[Number(params.id)];
    if (!records) return notFound('Employee');
    const body = (await request.json()) as { effective_from: string; note: string };
    return HttpResponse.json(
      {
        ...records[0],
        id: 99,
        version: Math.max(...records.map((record) => record.version)) + 1,
        effective_from: body.effective_from,
        note: body.note,
        is_current: false,
        is_scheduled: true,
        warnings: [],
      },
      { status: 201 },
    );
  }),
  http.get('/api/v1/employees/:id/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const employee = employeeDetails[Number(params.id)];
    return employee ? HttpResponse.json(employee) : notFound('Employee');
  }),
  http.post('/api/v1/employees/:id/exit/', async ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const employee = employeeDetails[Number(params.id)];
    if (!employee) return notFound('Employee');
    const { last_date } = (await request.json()) as { last_date: string };
    return HttpResponse.json({ ...employee, last_date });
  }),
  http.get('/api/v1/employees/:id/compensation/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const records = histories[Number(params.id)];
    return records ? HttpResponse.json(records) : notFound('Employee');
  }),
  http.get('/api/v1/employees/:id/audit/', ({ request, params }) =>
    authenticated(request, auditPage(Number(params.id))),
  ),
  http.delete('/api/v1/compensation/:id/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const record = Object.values(histories)
      .flat()
      .find((candidate) => candidate.id === Number(params.id));
    if (!record) return notFound('CompensationRecord');
    return HttpResponse.json({
      ...record,
      is_scheduled: false,
      cancelled_at: '2026-10-07T09:00:00+00:00',
      cancelled_by: HR_EMAIL,
    });
  }),
];

export const XLSX_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

export const importHandlers = [
  http.get('/api/v1/imports/', ({ request }) => authenticated(request, batchPage())),
  // The multipart body is not read: under Node's fetch a jsdom File does not survive the trip.
  http.post('/api/v1/imports/', ({ request }) => {
    if (!hasAccessToken(request)) return unauthorized();
    return HttpResponse.json(
      { ...reviewBatch, id: 7, file_name: 'november.xlsx', warnings: [] },
      { status: 201 },
    );
  }),
  // Before `:id`, which would otherwise take "template" as an id.
  http.get('/api/v1/imports/template/', ({ request }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const country = new URL(request.url).searchParams.get('country');
    const name = country ? `acme-import-template-${country}.xlsx` : 'acme-import-template.xlsx';
    return new HttpResponse(new Blob(['xlsx']), {
      headers: {
        'Content-Type': XLSX_TYPE,
        'Content-Disposition': `attachment; filename="${name}"`,
      },
    });
  }),
  http.get('/api/v1/imports/:id/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const batch = batches.find((candidate) => candidate.id === Number(params.id));
    return batch ? HttpResponse.json(batch) : notFound('ImportBatch');
  }),
  http.get('/api/v1/imports/:id/rows/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    if (!batches.some((candidate) => candidate.id === Number(params.id))) {
      return notFound('ImportBatch');
    }
    const rows = Number(params.id) === reviewBatch.id ? reviewRows : [];
    return HttpResponse.json(rowsPage(new URL(request.url), rows));
  }),
  http.post('/api/v1/imports/:id/rows/:rowId/:act/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const row = reviewRows.find((candidate) => candidate.id === Number(params.rowId));
    if (!row) return notFound('ImportRow');
    const status = params.act === 'skip' ? 'skipped' : row.validation_status;
    return HttpResponse.json({ ...row, status });
  }),
  http.post('/api/v1/imports/:id/approve/', ({ request }) => {
    if (!hasAccessToken(request)) return unauthorized();
    return HttpResponse.json({ detail: '1 row has errors', error_rows: 1 }, { status: 409 });
  }),
  http.post('/api/v1/imports/:id/discard/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const batch = batches.find((candidate) => candidate.id === Number(params.id));
    if (!batch) return notFound('ImportBatch');
    return HttpResponse.json({ ...batch, status: 'discarded' });
  }),
];

export const insightHandlers = [
  http.get('/api/v1/insights/:name/', ({ request, params }) => {
    if (!hasAccessToken(request)) return unauthorized();
    const exited = new URL(request.url).searchParams.get('include_exited') === 'true';
    const payload = insightFor(String(params.name), exited);
    return payload ? HttpResponse.json(payload) : notFound('insight');
  }),
];

export const handlers = [
  http.get('/healthz', () => HttpResponse.json({ status: 'ok' })),
  ...authHandlers,
  ...metaHandlers,
  ...employeeHandlers,
  ...importHandlers,
  ...insightHandlers,
];
