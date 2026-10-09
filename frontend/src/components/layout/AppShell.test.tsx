import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { setSession } from '../../lib/auth';
import { renderApp } from '../../test/render';

describe('AppShell', () => {
  it('keeps the nav and the top bar out of main, the one scroll container', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/employees');

    const main = await screen.findByRole('main');
    expect(main).not.toContainElement(screen.getByRole('navigation', { name: 'Main' }));
    expect(main).not.toContainElement(screen.getByRole('banner'));
    expect(
      within(screen.getByRole('banner')).getByRole('button', { name: 'Sign out' }),
    ).toBeInTheDocument();
    // Focusable from code, out of the tab order (D75).
    expect(main).toHaveAttribute('tabindex', '-1');
    // The containing block of whatever a page positions, so nothing scrolls the window.
    expect(main).toHaveStyle({ position: 'relative', overflowY: 'auto' });
  });

  it('puts main back at the top and focuses it when the page changes', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    renderApp('/employees');
    const user = userEvent.setup();
    await screen.findByRole('heading', { level: 1, name: 'Employees' });
    const main = screen.getByRole('main');
    main.scrollTop = 300;

    await user.click(screen.getByRole('link', { name: 'Imports' }));

    await screen.findByRole('heading', { level: 1, name: 'Imports' });
    expect(main.scrollTop).toBe(0);
    // Page Down and Space now scroll the new page without a click.
    expect(main).toHaveFocus();
  });

  it('keeps the place on the page when only the filters change', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    const { router } = renderApp('/employees');
    await screen.findByRole('heading', { level: 1, name: 'Employees' });
    const main = screen.getByRole('main');
    main.scrollTop = 300;

    await router.navigate('/employees?status=any');

    expect(router.state.location.search).toBe('?status=any');
    expect(main.scrollTop).toBe(300);
  });
});
