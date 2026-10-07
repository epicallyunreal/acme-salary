import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';

import { setUnauthenticatedHandler } from './api/client';
import { SessionGate } from './components/layout/SessionGate';
import { loginPath } from './lib/navigation';
import { theme } from './lib/theme';
import { createAppRouter } from './router';

// Created once, outside the component tree (React Router's data routers must not live in state).
const router = createAppRouter();
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// A request that fails twice with 401 ends the session and brings the user back here afterwards.
setUnauthenticatedHandler(() => {
  queryClient.clear();
  void router.navigate(loginPath(router.state.location), { replace: true });
});

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <SessionGate>
          <RouterProvider router={router} />
        </SessionGate>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
