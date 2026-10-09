import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';

import { BusyProvider } from './components/busy/BusyProvider';

import { SessionGate } from './components/layout/SessionGate';
import { createQueryClient } from './lib/queryClient';
import { redirectToLoginOnSecond401 } from './lib/session';
import { theme } from './lib/theme';
import { createAppRouter } from './router';

// Created once, outside the component tree (React Router's data routers must not live in state).
const router = createAppRouter();
const queryClient = createQueryClient();

redirectToLoginOnSecond401(router, queryClient);

export default function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <QueryClientProvider client={queryClient}>
        <SessionGate>
          <BusyProvider>
            <RouterProvider router={router} />
          </BusyProvider>
        </SessionGate>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
