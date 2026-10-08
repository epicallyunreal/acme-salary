import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

import { redirectToLoginOnSecond401 } from '../lib/session';
import { theme } from '../lib/theme';
import { SessionGate } from '../components/layout/SessionGate';
import { routes } from '../router';

/** Retries off so a failing request fails the test at once. */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
}

function Providers({ children, client }: { children: ReactNode; client: QueryClient }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}

interface ProviderOptions extends Omit<RenderOptions, 'wrapper'> {
  /** The URL the component is rendered at, so `useSearchParams` and links work. */
  route?: string;
}

/** Renders one component inside the theme, a query client and a memory router at `route`. */
export function renderWithProviders(
  ui: ReactElement,
  { route = '/', ...options }: ProviderOptions = {},
) {
  const client = createTestQueryClient();
  const router = createMemoryRouter([{ path: '*', element: ui }], { initialEntries: [route] });
  const utils = render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
    options,
  );
  return { ...utils, router, client };
}

/** Renders the real route table in memory, starting at `initialEntry`, the way the app runs.
 * `gate` adds the SessionGate, so the refresh on load runs first. */
export function renderApp(
  initialEntry = '/',
  { gate = false, state }: { gate?: boolean; state?: unknown } = {},
) {
  const client = createTestQueryClient();
  const entry = state === undefined ? initialEntry : { pathname: initialEntry, state };
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  redirectToLoginOnSecond401(router, client);
  const app = <RouterProvider router={router} />;
  const utils = render(
    <Providers client={client}>{gate ? <SessionGate>{app}</SessionGate> : app}</Providers>,
  );
  return { ...utils, router, client };
}
