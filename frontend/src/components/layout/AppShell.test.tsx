import { act, screen, within } from '@testing-library/react';
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
    // As tall as the root and never narrower than 1024 px: a narrower window scrolls sideways,
    // and only sideways (D75).
    expect(main.parentElement?.parentElement).toHaveStyle({
      height: '100%',
      minWidth: '1024px',
      overflow: 'hidden',
    });
    expect(document.body).toHaveStyle({ height: '100%' });
  });

  it('credits its builder at the foot of the nav, opening in a new tab (D80)', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/employees');

    const nav = await screen.findByRole('navigation', { name: 'Main' });
    const credit = within(nav).getByRole('link', {
      name: 'Built by Nutan Prabhat, opens in a new tab',
    });
    // The last thing in the nav, after Help.
    const links = within(nav).getAllByRole('link');
    expect(links.at(-1)).toBe(credit);
    // The nav scrolls on its own when the window is short, so the credit never covers an item.
    expect(nav).toHaveStyle({ overflowY: 'auto', display: 'flex', flexDirection: 'column' });
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

    // Inside act, so React renders the new address and runs its effects before the check.
    await act(() => router.navigate('/employees?status=any'));

    expect(router.state.location.search).toBe('?status=any');
    expect(main.scrollTop).toBe(300);
  });
});
