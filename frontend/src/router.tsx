import { createBrowserRouter, Navigate, type RouteObject } from 'react-router';

import { AppShell } from './components/layout/AppShell';
import { RequireAuth } from './components/layout/RequireAuth';
import { EmployeeDetail } from './pages/EmployeeDetail';
import { Employees } from './pages/Employees';
import { Imports } from './pages/Imports';
import { Login } from './pages/Login';
import { NewEmployee } from './pages/NewEmployee';
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
          { path: '/employees/new', element: <NewEmployee /> },
          { path: '/employees/:id', element: <EmployeeDetail /> },
          { path: '/imports', element: <Imports /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
