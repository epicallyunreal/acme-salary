import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll } from 'vitest';

import { setUnauthenticatedHandler } from '../api/client';
import { clearSession } from '../lib/auth';
import { handlers } from './handlers';

// Every API call in a test is answered by MSW; an unhandled request fails the test.
export const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  clearSession();
  setUnauthenticatedHandler(() => {});
});
afterAll(() => server.close());
