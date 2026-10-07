import type { QueryClient } from '@tanstack/react-query';
import type { createMemoryRouter } from 'react-router';

import { setUnauthenticatedHandler } from '../api/client';
import { loginPath } from './navigation';

type DataRouter = ReturnType<typeof createMemoryRouter>;

/** A request that fails twice with 401 ends the session; the user lands on login and comes back. */
export function redirectToLoginOnSecond401(router: DataRouter, client: QueryClient) {
  setUnauthenticatedHandler(() => {
    client.clear();
    void router.navigate(loginPath(router.state.location), { replace: true });
  });
}
