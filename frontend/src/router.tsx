import { createBrowserRouter, type RouteObject } from 'react-router';

import { AppShell } from './components/layout/AppShell';
import { RequireAuth } from './components/layout/RequireAuth';
import { Dashboard } from './pages/Dashboard';
import { DemoData } from './pages/DemoData';
import { EmployeeDetail } from './pages/EmployeeDetail';
import { Employees } from './pages/Employees';
import { ImportReview } from './pages/ImportReview';
import { Imports } from './pages/Imports';
import { Login } from './pages/Login';
import { NewEmployee } from './pages/NewEmployee';
import { NotFound } from './pages/NotFound';

// DESIGN section 6 route table.
export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Dashboard /> },
          { path: '/employees', element: <Employees /> },
          { path: '/employees/new', element: <NewEmployee /> },
          { path: '/employees/:id', element: <EmployeeDetail /> },
          { path: '/imports', element: <Imports /> },
          { path: '/imports/:id', element: <ImportReview /> },
          { path: '/demo', element: <DemoData /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}
