import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';

import { SessionGate } from './components/layout/SessionGate';
import { redirectToLoginOnSecond401 } from './lib/session';
import { theme } from './lib/theme';
import { createAppRouter } from './router';

// Created once, outside the component tree (React Router's data routers must not live in state).
const router = createAppRouter();
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

redirectToLoginOnSecond401(router, queryClient);

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
