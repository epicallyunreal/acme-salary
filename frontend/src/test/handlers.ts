import { http, HttpResponse } from 'msw/http';

// One handler per API route the app calls. Each step adds its routes with realistic fixtures.
export const handlers = [http.get('/healthz', () => HttpResponse.json({ status: 'ok' }))];
