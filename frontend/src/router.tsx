import { LinearProgress } from '@mui/material';
import { createBrowserRouter, type RouteObject } from 'react-router';

import { AppShell } from './components/layout/AppShell';
import { RequireAuth } from './components/layout/RequireAuth';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';

// Each page is its own chunk, loaded on first visit, so the grid and the charts ship only with
// the pages that draw them (D73). The login and the shell stay in the first bundle, and each
// import names its export, so a misspelling is a type error rather than a blank route.
export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    hydrateFallbackElement: <LinearProgress aria-label="Loading the page" />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            index: true,
            lazy: async () => ({ Component: (await import('./pages/Dashboard')).Dashboard }),
          },
          {
            path: '/employees',
            lazy: async () => ({ Component: (await import('./pages/Employees')).Employees }),
          },
          {
            path: '/employees/new',
            lazy: async () => ({ Component: (await import('./pages/NewEmployee')).NewEmployee }),
          },
          {
            path: '/employees/:id',
            lazy: async () => ({
              Component: (await import('./pages/EmployeeDetail')).EmployeeDetail,
            }),
          },
          {
            path: '/imports',
            lazy: async () => ({ Component: (await import('./pages/Imports')).Imports }),
          },
          {
            path: '/imports/:id',
            lazy: async () => ({ Component: (await import('./pages/ImportReview')).ImportReview }),
          },
          {
            path: '/demo',
            lazy: async () => ({ Component: (await import('./pages/DemoData')).DemoData }),
          },
          {
            path: '/help',
            lazy: async () => ({ Component: (await import('./pages/Help')).Help }),
          },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
