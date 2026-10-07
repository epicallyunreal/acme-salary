import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { getAccessToken, setSession } from '../../lib/auth';
import { renderApp } from '../../test/render';

describe('RequireAuth', () => {
  it('sends a signed-out visitor to the login page and remembers where they were', async () => {
    const { router } = renderApp('/employees?page=3');

    await screen.findByRole('heading', { name: 'ACME Salary' });
    const { pathname, search } = router.state.location;
    expect(pathname).toBe('/login');
    expect(new URLSearchParams(search).get('next')).toBe('/employees?page=3');
  });

  it('shows the shell with the signed-in email and signs out', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    const { router } = renderApp('/employees');
    const user = userEvent.setup();

    await screen.findByText('hr@acme.example');
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Employees' })).toHaveAttribute('aria-current', 'page');

    await user.click(screen.getByRole('button', { name: 'Sign out' }));

    await screen.findByRole('heading', { name: 'ACME Salary' });
    expect(router.state.location.pathname).toBe('/login');
    expect(getAccessToken()).toBeNull();
  });

  it('shows the not-found page inside the shell for an unknown address', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/nowhere');

    await screen.findByRole('heading', { name: 'Page not found' });
    expect(screen.getByRole('link', { name: 'Go to the directory' })).toHaveAttribute(
      'href',
      '/employees',
    );
  });
});
