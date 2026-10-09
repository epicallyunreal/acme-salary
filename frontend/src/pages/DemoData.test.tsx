import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { POLL } from '../lib/poll';
import { resetCounts, sampleFiles, sampleFilesEmpty } from '../test/fixtures/demo';
import { batchPage } from '../test/fixtures/imports';
import { expectClosed, expectFailed, expectPending, held } from '../test/busy';
import { HR_PASSWORD } from '../test/handlers';
import { renderApp } from '../test/render';
import { server } from '../test/setup';
import { expectEveryFieldLabelled, expectFocusCycle } from '../test/a11y';

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

  const defaults = { ...POLL };
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.assign(POLL, defaults);
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
      screen.getByText(
        /no pay changes until revision files are imported, and Spent in period reads high, today's pay counted back to joining\./,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Empty the database and start with the base/)).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Dashboard', 'Employees', 'Imports', 'Demo data', 'Help']);
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

  it('downloads a file with the token, under the name the API gives it', async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    let authorization: string | null = null;
    server.use(
      http.get('/api/v1/admin/sample-files/exits/', ({ request }) => {
        authorization = request.headers.get('authorization');
        return new HttpResponse(new Blob(['xlsx']), {
          headers: { 'Content-Disposition': 'attachment; filename="exits-20261007.xlsx"' },
        });
      }),
    );
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Download exits.xlsx' }));

    await waitFor(() => expect(saved).toEqual(['exits-20261007.xlsx']));
    expect(authorization).toBe('Bearer access-1');
  });

  it('downloads behind the busy dialog, and says so when the file cannot be made', async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    const { handler, release } = held(
      () =>
        new HttpResponse(new Blob(['xlsx']), {
          headers: { 'Content-Disposition': 'attachment; filename="exits.xlsx"' },
        }),
    );
    server.use(http.get('/api/v1/admin/sample-files/exits/', handler));
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Download exits.xlsx' }));

    await expectPending('Preparing exits.xlsx\u2026');
    expect(
      screen.getByRole('button', { name: 'Download base-15000.xlsx', hidden: true }),
    ).toBeDisabled();
    release();
    await expectClosed('Preparing exits.xlsx\u2026');
    await waitFor(() => expect(saved).toEqual(['exits.xlsx']));

    server.use(
      http.get('/api/v1/admin/sample-files/exits/', () =>
        HttpResponse.json({ detail: 'import the base file first' }, { status: 409 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: 'Download exits.xlsx' }));

    await expectFailed('Could not download exits.xlsx', 'import the base file first');
  });

  it('turns Empty the database on only for exactly RESET beside a password', async () => {
    const user = userEvent.setup();
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    const submit = within(dialog).getByRole('button', { name: 'Empty the database' });
    const password = within(dialog).getByLabelText('Your password');
    const confirm = within(dialog).getByLabelText('Type RESET to confirm');

    await user.type(confirm, 'RESET');
    expect(submit).toBeDisabled();
    await user.type(password, 'x');
    expect(submit).toBeEnabled();
    for (const wrong of ['reset', 'RESET ', 'RESE']) {
      await user.clear(confirm);
      await user.type(confirm, wrong);
      expect(submit).toBeDisabled();
    }
    await user.clear(confirm);
    await user.type(confirm, 'RESET');
    expect(submit).toBeEnabled();
  });

  it('empties behind the busy dialog, which nothing dismisses until the server answers', async () => {
    const { handler, release } = held(() => HttpResponse.json(resetCounts));
    server.use(
      http.post('/api/v1/admin/reset-demo/', handler),
      http.get('/api/v1/imports/', () => HttpResponse.json(batchPage([]))),
    );
    const user = userEvent.setup();
    const { router } = renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    await within(dialog).findByText(DELETES);
    await user.type(within(dialog).getByLabelText('Your password'), HR_PASSWORD);
    await user.type(within(dialog).getByLabelText('Type RESET to confirm'), 'RESET');
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    await expectPending('Emptying the database\u2026');
    expect(
      within(dialog).getByRole('button', { name: 'Cancel', hidden: true }),
    ).toBeInTheDocument();
    release();
    await expectClosed('Emptying the database\u2026');
    await waitFor(() => expect(router.state.location.pathname).toBe('/imports'));
  });

  it('empties the database behind the password and RESET, then goes to Imports', async () => {
    // Emptied, the imports list is empty too, which is when Imports shows the notice.
    server.use(http.get('/api/v1/imports/', () => HttpResponse.json(batchPage([]))));
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
    await user.type(confirm, 'RESET');
    expect(submit).toBeEnabled();

    await user.click(submit);

    // The server's 403 shows in the busy dialog, then on the field once it is closed.
    await expectFailed('The database was not emptied', 'password did not match');
    await waitFor(() => expect(password).toHaveAccessibleDescription('password did not match'));
    expect(router.state.location.pathname).toBe('/demo');

    await user.clear(password);
    await user.type(password, HR_PASSWORD);
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/imports'));
    expect(
      await screen.findByText('The database is empty. Import base-15000.xlsx to start.'),
    ).toBeInTheDocument();
  });

  it('keeps waiting through a cut reset until the counts reach zero, then goes to Imports', async () => {
    POLL.every = 10;
    POLL.upTo = 2000;
    let posted = false;
    const emptied = {
      ...resetCounts,
      employees: 0,
      compensation_records: 0,
      compensation_lines: 0,
      import_batches: 0,
      import_rows: 0,
      audit_entries: 1,
    };
    server.use(
      http.get('/api/v1/admin/reset-demo/', () =>
        HttpResponse.json(posted ? emptied : resetCounts),
      ),
      http.post('/api/v1/admin/reset-demo/', () => {
        posted = true;
        return HttpResponse.error();
      }),
      http.get('/api/v1/imports/', () => HttpResponse.json(batchPage([]))),
    );
    const user = userEvent.setup();
    const { router } = renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    await within(dialog).findByText(DELETES);
    await user.type(within(dialog).getByLabelText('Your password'), HR_PASSWORD);
    await user.type(within(dialog).getByLabelText('Type RESET to confirm'), 'RESET');
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Still working\u2026');
    await waitFor(() => expect(router.state.location.pathname).toBe('/imports'));
    expect(
      await screen.findByText('The database is empty. Import base-15000.xlsx to start.'),
    ).toBeInTheDocument();
  });

  it('gives up on a cut reset after the wait and says where to look', async () => {
    POLL.every = 10;
    POLL.upTo = 60;
    server.use(http.post('/api/v1/admin/reset-demo/', () => HttpResponse.error()));
    const user = userEvent.setup();
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    await within(dialog).findByText(DELETES);
    await user.type(within(dialog).getByLabelText('Your password'), HR_PASSWORD);
    await user.type(within(dialog).getByLabelText('Type RESET to confirm'), 'RESET');
    await user.click(within(dialog).getByRole('button', { name: 'Empty the database' }));

    await expectFailed(
      'The database was not emptied',
      'The server may still be working, or the reset was refused; reload the page and check the counts.',
    );
  });

  it('starts clean when reopened after a cancel', async () => {
    const user = userEvent.setup();
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    let dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    await user.type(within(dialog).getByLabelText('Your password'), 'secret');
    await user.click(within(dialog).getByRole('button', { name: 'Show password' }));
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Empty the database' }));

    dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    expect(within(dialog).getByLabelText('Your password')).toHaveValue('');
    expect(within(dialog).getByLabelText('Your password')).toHaveAttribute('type', 'password');
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

    await expectFailed(
      'The database was not emptied',
      'Too many attempts. Wait an hour and try again.',
    );
  });
  it('says so when the sample files do not load, and the retry loads them', async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get('/api/v1/admin/sample-files/', () =>
        failing ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(sampleFiles),
      ),
    );
    renderApp('/demo');

    expect(
      await screen.findByText(
        'Could not load the sample files. Check your connection and try again.',
      ),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('list', { name: 'Sample files' })).toBeInTheDocument();
  });

  it('says so in the dialog when the counts do not load, and the retry loads them', async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get('/api/v1/admin/reset-demo/', () =>
        failing ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(resetCounts),
      ),
    );
    renderApp('/demo');

    await user.click(await screen.findByRole('button', { name: 'Empty the database' }));
    const dialog = await screen.findByRole('dialog', { name: 'Empty the database?' });
    expect(
      await within(dialog).findByText(
        'Could not load the counts. Check your connection and try again.',
      ),
    ).toBeInTheDocument();
    failing = false;
    await user.click(within(dialog).getByRole('button', { name: 'Retry' }));

    expect(await within(dialog).findByText(DELETES)).toBeInTheDocument();
    expectEveryFieldLabelled(dialog);
  });

  it('the reset dialog takes focus and hands it back on Escape', async () => {
    const user = userEvent.setup();
    renderApp('/demo');
    const button = await screen.findByRole('button', { name: 'Empty the database' });

    await expectFocusCycle(user, button, 'Empty the database?');
  });
});
