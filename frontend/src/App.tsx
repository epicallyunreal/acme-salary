import { CssBaseline, ThemeProvider } from '@mui/material';
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';

import { BusyProvider } from './components/busy/BusyProvider';

import { SessionGate } from './components/layout/SessionGate';
import { pageLoaded, recoverFromPreloadError } from './lib/preloadRecovery';
import { createQueryClient } from './lib/queryClient';
import { redirectToLoginOnSecond401 } from './lib/session';
import { theme } from './lib/theme';
import { createAppRouter } from './router';

// Created once, outside the component tree (React Router's data routers must not live in state).
const router = createAppRouter();
const queryClient = createQueryClient();

redirectToLoginOnSecond401(router, queryClient);
window.addEventListener('vite:preloadError', (event) => recoverFromPreloadError(event));
// A navigation that settles without an error means the build's code loads (D78).
router.subscribe((state) => {
  if (state.navigation.state === 'idle' && state.errors === null) pageLoaded();
});

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
