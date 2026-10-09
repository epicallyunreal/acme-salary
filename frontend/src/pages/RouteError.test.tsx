import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { reloadPage } from '../lib/navigation';
import { renderApp } from '../test/render';

// Any page will do: the unknown route's is the one with no data to stand up.
vi.mock('./NotFound', () => ({
  NotFound: () => {
    throw new Error('the page broke');
  },
}));
vi.mock('../lib/navigation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/navigation')>()),
  reloadPage: vi.fn(),
}));

describe('RouteError', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it("shows the app's own page inside the frame when a page fails to render (D76)", async () => {
    const { router } = renderApp('/nowhere');
    const user = userEvent.setup();

    expect(await screen.findByText('This page could not be shown.')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Something went wrong' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.queryByText('the page broke')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reload' }));
    expect(reloadPage).toHaveBeenCalledOnce();

    await user.click(screen.getByRole('link', { name: 'Go to the dashboard' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
  });
});
