import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, expect } from 'vitest';

import { setUnauthenticatedHandler } from '../api/client';
import { clearSession } from '../lib/auth';
import { handlers } from './handlers';

// The pre-commit gate runs the suite beside other work. On a loaded machine a page with a grid takes
// longer than Testing Library's 1 s default to render, so a wait gets 3 s before it fails.
configure({ asyncUtilTimeout: 3000 });

// Every API call in a test is answered by MSW; an unhandled request fails the test that made it.
export const server = setupServer(...handlers);
const unhandled: string[] = [];

beforeAll(() =>
  server.listen({
    onUnhandledFrame: ({ frame, defaults }) => {
      const request = (frame as { request?: Request }).request;
      unhandled.push(request ? `${request.method} ${request.url}` : 'a non-HTTP frame');
      defaults.error();
    },
  }),
);
afterEach(() => {
  server.resetHandlers();
  cleanup();
  clearSession();
  setUnauthenticatedHandler(() => {});
  const seen = unhandled.splice(0);
  expect(seen, 'requests no handler answered').toEqual([]);
});
afterAll(() => server.close());
