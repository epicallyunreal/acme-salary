import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

import { setUnauthenticatedHandler } from '../api/client';
import { loginPath } from '../lib/navigation';
import { theme } from '../lib/theme';
import { createTestRouter } from '../router';

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

/** Renders the real route table in memory, starting at `initialEntry`, the way the app runs. */
export function renderApp(initialEntry = '/') {
  const client = createTestQueryClient();
  const router = createTestRouter([initialEntry]);
  setUnauthenticatedHandler(() => {
    client.clear();
    void router.navigate(loginPath(router.state.location), { replace: true });
  });
  const utils = render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  );
  return { ...utils, router, client };
}
