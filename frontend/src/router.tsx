import { createBrowserRouter, type RouteObject } from 'react-router';

import { AppShell } from './components/layout/AppShell';
import { RequireAuth } from './components/layout/RequireAuth';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';

// Each page is its own chunk, loaded on first visit, so the grid and the charts ship only with
// the pages that draw them (D73). The login and the shell stay in the first bundle.
const page = (load: () => Promise<Record<string, unknown>>, name: string) => async () => ({
  Component: (await load())[name] as React.ComponentType,
});

// DESIGN section 6 route table.
export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, lazy: page(() => import('./pages/Dashboard'), 'Dashboard') },
          { path: '/employees', lazy: page(() => import('./pages/Employees'), 'Employees') },
          {
            path: '/employees/new',
            lazy: page(() => import('./pages/NewEmployee'), 'NewEmployee'),
          },
          {
            path: '/employees/:id',
            lazy: page(() => import('./pages/EmployeeDetail'), 'EmployeeDetail'),
          },
          { path: '/imports', lazy: page(() => import('./pages/Imports'), 'Imports') },
          {
            path: '/imports/:id',
            lazy: page(() => import('./pages/ImportReview'), 'ImportReview'),
          },
          { path: '/demo', lazy: page(() => import('./pages/DemoData'), 'DemoData') },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
