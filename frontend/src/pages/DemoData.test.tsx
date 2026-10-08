import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { sampleFilesEmpty } from '../test/fixtures/demo';
import { HR_PASSWORD } from '../test/handlers';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

/** jsdom has no object URLs and does not follow links, so each save is caught at the click. */
function catchSaves(): string[] {
  vi.stubGlobal(
    'URL',
    Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => 'blob:download'),
      revokeObjectURL: vi.fn(),
    }),
  );
  const saved: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push(this.download);
  });
  return saved;
}

const DELETES =
  'This deletes 15,000 employees, 51,659 compensation records, 128,000 lines, 3 import batches with 150 rows and 70,000 audit entries. Lookups, exchange rates and your login stay.';

describe('DemoData', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('lists the seven sample files with what each exercises, after Imports in the nav', async () => {
    renderApp('/demo');

    expect(await screen.findByRole('heading', { level: 1, name: 'Demo data' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'The demo runs on a small shared machine, and a large import can take a few minutes.',
      ),
    ).toBeInTheDocument();
    const list = await screen.findByRole('list', { name: 'Sample files' });
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(7);
    expect(within(items[0]).getByText('base-15000.xlsx')).toBeInTheDocument();
    expect(within(items[0]).getByText(/the scale test/)).toBeInTheDocument();
    expect(within(items[6]).getByRole('button', { name: 'Download fix-me.xlsx' })).toBeEnabled();
    expect(
      screen.getByText(/no pay changes until revision files are imported/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Empty the database and start with the base/)).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Dashboard', 'Employees', 'Imports', 'Demo data']);
    expect(screen.getByRole('link', { name: 'Demo data' })).toHaveAttribute('aria-current', 'page');
  });

  it('disables the generated files until the base file is imported', async () => {
    server.use(http.get('/api/v1/admin/sample-files/', () => HttpResponse.json(sampleFilesEmpty)));
    renderApp('/demo');

    const list = await screen.findByRole('list', { name: 'Sample files' });

    expect(within(list).getByRole('button', { name: 'Download base-15000.xlsx' })).toBeEnabled();
    expect(within(list).getByRole('button', { name: 'Download exits.xlsx' })).toBeDisabled();
    expect(within(list).getAllByText('Import the base file first.')).toHaveLength(6);
  });

  it('downloads a file under the name the API gives it', async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Download exits.xlsx' }));

    await waitFor(() => expect(saved).toEqual(['exits.xlsx']));
  });

  it('empties the database behind the password and RESET, then goes to Imports', async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    expect(await within(dialog).findByText(DELETES)).toBeInTheDocument();
    const submit = within(dialog).getByRole('button', { name: 'Empty the database' });
    const password = within(dialog).getByLabelText('Your password');
    const confirm = within(dialog).getByLabelText('Type RESET to confirm');
    expect(submit).toBeDisabled();
    await user.type(password, 'wrong');
    expect(submit).toBeDisabled();
    await user.type(confirm, 'reset');
    expect(submit).toBeEnabled();

    await user.click(submit);

    expect(await within(dialog).findByText('password did not match')).toBeInTheDocument();
    expect(within(dialog).getByText('type RESET to confirm')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/demo');

    await user.clear(password);
    await user.type(password, HR_PASSWORD);
    await user.clear(confirm);
    await user.type(confirm, 'RESET');
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/imports'));
    expect(
      await screen.findByText('The database is empty. Import base-15000.xlsx to start.'),
    ).toBeInTheDocument();
  });

  it('shows the password on request and says when the attempts run out', async () => {
    server.use(
      http.post('/api/v1/admin/reset-demo/', () =>
        HttpResponse.json({ detail: 'Request was throttled.' }, { status: 429 }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    const password = within(dialog).getByLabelText('Your password');
    expect(password).toHaveAttribute('type', 'password');
    await user.click(within(dialog).getByRole('button', { name: 'Show password' }));
    expect(password).toHaveAttribute('type', 'text');
    await user.type(password, 'x');
    await user.type(within(dialog).getByLabelText('Type RESET to confirm'), 'RESET');
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    expect(
      await within(dialog).findByText('Too many attempts. Wait an hour and try again.'),
    ).toBeInTheDocument();
  });
});
