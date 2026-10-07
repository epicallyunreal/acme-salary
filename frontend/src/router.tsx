import { createBrowserRouter, createMemoryRouter, Navigate, type RouteObject } from 'react-router';

import { AppShell } from './components/layout/AppShell';
import { RequireAuth } from './components/layout/RequireAuth';
import { Employees } from './pages/Employees';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';

// DESIGN section 6 route table. `/` sends to the directory until the dashboard lands in step 6.
export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/employees" replace /> },
          { path: '/employees', element: <Employees /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}

/** The same routes in memory, for tests that start at a given URL. */
export function createTestRouter(initialEntries: string[]) {
  return createMemoryRouter(routes, { initialEntries });
}
