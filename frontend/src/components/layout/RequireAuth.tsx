import { Navigate, Outlet, useLocation } from 'react-router';

import { useAccessToken } from '../../lib/auth';
import { loginPath } from '../../lib/navigation';

/** Signed-out visitors go to the login page and come back to where they were. */
export function RequireAuth() {
  const token = useAccessToken();
  const location = useLocation();
  if (token === null) return <Navigate to={loginPath(location)} replace />;
  return <Outlet />;
}
