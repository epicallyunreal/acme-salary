import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { POLL } from '../lib/poll';
import { batchPage, batches, reviewBatch } from '../test/fixtures/imports';
import { XLSX_TYPE } from '../test/handlers';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

function sheet(name: string, type: string, content = 'legacy_code') {
  return new File([content], name, { type });
}

function chooseFile(file: File) {
  fireEvent.change(screen.getByLabelText('Spreadsheet to import'), { target: { files: [file] } });
}

describe('Imports', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  const defaults = { ...POLL };
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    Object.assign(POLL, defaults);
  });

  it('lists every batch newest first with its status, counts and ignored columns', async () => {
    renderApp('/imports');

    const table = await screen.findByRole('table', { name: 'Imports' });
    const [review, approved, discarded] = within(table).getAllByRole('row').slice(1);
    expect(within(review).getByRole('link', { name: 'october-raises.xlsx' })).toHaveAttribute(
      'href',
      '/imports/3',
    );
    expect(within(review).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    expect(within(review).getByText('review')).toBeInTheDocument();
    // 09:12 UTC in the tests' America/New_York.
    expect(within(review).getByText('7 Oct 2026, 05:12')).toBeInTheDocument();
    expect(within(approved).getByText('approved')).toBeInTheDocument();
    expect(within(approved).getAllByText('12')).toHaveLength(2);
    expect(within(discarded).getByText('discarded')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Imports' })).toHaveAttribute('aria-current', 'page');
  });

  it('says what to do when there are no imports yet', async () => {
    server.use(http.get('/api/v1/imports/', () => HttpResponse.json(batchPage([]))));
    renderApp('/imports');

    expect(
      await screen.findByText(
        'No imports yet. Download the template, fill it in and drop it here.',
      ),
    ).toBeInTheDocument();
  });

  it('stages a chosen file and opens its review page', async () => {
    // jsdom's File cannot be read back out of a multipart body under Node's fetch, so the form
    // is checked as the client builds it and the request by its type.
    const appended = vi.spyOn(FormData.prototype, 'append');
    const sent: (string | null)[] = [];
    server.use(
      http.post('/api/v1/imports/', ({ request }) => {
        sent.push(request.headers.get('content-type'));
        return HttpResponse.json({ ...reviewBatch, id: 7 }, { status: 201 });
      }),
    );
    const { router } = renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });

    chooseFile(sheet('november.xlsx', XLSX_TYPE));

    await waitFor(() => expect(router.state.location.pathname).toBe('/imports/7'));
    expect(appended.mock.calls.map(([name, value]) => [name, (value as File).name])).toEqual([
      ['file', 'november.xlsx'],
    ]);
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatch(/^multipart\/form-data; boundary=/);
  });

  it('takes a file dropped on the zone as well', async () => {
    const { router } = renderApp('/imports');
    const zone = await screen.findByRole('group', { name: 'Drop a spreadsheet here' });

    fireEvent.drop(zone, {
      dataTransfer: { files: [sheet('dropped.csv', 'text/csv')] },
    });

    await waitFor(() => expect(router.state.location.pathname).toBe('/imports/7'));
  });

  it("lists the server's reasons when a file is refused, in a summary that takes focus", async () => {
    server.use(
      http.post('/api/v1/imports/', () =>
        HttpResponse.json(
          {
            missing_columns: ['Missing required column: country_code'],
            unknown_columns: ['Ignored unknown column: Remarks'],
          },
          { status: 400 },
        ),
      ),
    );
    renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });

    chooseFile(sheet('october.csv', 'text/csv'));

    const summary = await screen.findByRole('alert');
    expect(summary).toHaveTextContent('The file was not staged');
    expect(
      within(summary)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual(['Missing required column: country_code', 'Ignored unknown column: Remarks']);
    expect(summary).toHaveFocus();
  });

  it('says what the upload box takes', async () => {
    renderApp('/imports');

    expect(
      await screen.findByText(
        'Drop a .xlsx or .csv here, or choose a file. Up to 15,000 rows and 10 MB.',
      ),
    ).toBeInTheDocument();
  });

  it('refuses a file over 10 MB without sending it', async () => {
    let posted = false;
    server.use(
      http.post('/api/v1/imports/', () => {
        posted = true;
        return HttpResponse.json(reviewBatch, { status: 201 });
      }),
    );
    renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });
    const big = sheet('big.csv', 'text/csv');
    Object.defineProperty(big, 'size', { value: 10 * 1024 * 1024 + 1 });

    chooseFile(big);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'upload is larger than the 10 MB limit',
    );
    expect(posted).toBe(false);
  });

  it("downloads a country's template with the session's token", async () => {
    const user = userEvent.setup();
    const asked: string[] = [];
    server.use(
      http.get('/api/v1/imports/template/', ({ request }) => {
        asked.push(
          `${new URL(request.url).searchParams.get('country')} ${request.headers.get('authorization')}`,
        );
        return new HttpResponse(new Blob(['xlsx']), {
          headers: { 'Content-Disposition': 'attachment; filename="acme-import-template-IN.xlsx"' },
        });
      }),
    );
    // jsdom has no object URLs and does not follow links.
    vi.stubGlobal(
      'URL',
      Object.assign(class extends URL {}, {
        createObjectURL: vi.fn(() => 'blob:template'),
        revokeObjectURL: vi.fn(),
      }),
    );
    const saved: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      saved.push(this.download);
    });
    renderApp('/imports');

    await user.click(await screen.findByRole('button', { name: 'Download template' }));
    await user.click(await screen.findByRole('menuitem', { name: 'India (INR)' }));

    await waitFor(() => expect(saved).toEqual(['acme-import-template-IN.xlsx']));
    expect(asked).toEqual(['IN Bearer access-1']);
  });

  it('offers a retry when the imports do not load, and the retry loads them', async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get('/api/v1/imports/', () =>
        failing ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(batchPage()),
      ),
    );
    renderApp('/imports');

    expect(
      await screen.findByText('Could not load the imports. Check your connection and try again.'),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('table', { name: 'Imports' })).toBeInTheDocument();
  });

  it.each([
    [
      'the server refuses the size',
      () => HttpResponse.json({ detail: 'upload is larger than the 10 MB limit' }, { status: 413 }),
      'upload is larger than the 10 MB limit',
    ],
    [
      'the file has too many rows',
      () =>
        HttpResponse.json({ rows: ['file has 15,450 data rows, limit 15,000'] }, { status: 400 }),
      'file has 15,450 data rows, limit 15,000',
    ],
    [
      'another file is being read',
      () =>
        HttpResponse.json(
          { detail: 'another file is being read; try again in a moment' },
          { status: 409 },
        ),
      'another file is being read; try again in a moment',
    ],
  ])('says so when %s', async (_case, answer, message) => {
    server.use(http.post('/api/v1/imports/', answer));
    renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });

    chooseFile(sheet('october.csv', 'text/csv'));

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });

  it('keeps waiting through a cut upload and opens the batch the server made', async () => {
    POLL.every = 10;
    POLL.upTo = 2000;
    let polls = 0;
    const made = { ...reviewBatch, id: 4, file_name: 'october.csv' };
    server.use(
      http.post('/api/v1/imports/', () => HttpResponse.error()),
      http.get('/api/v1/imports/', () => {
        polls += 1;
        return HttpResponse.json(batchPage(polls >= 3 ? [made, ...batches] : batches));
      }),
    );
    const { router } = renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });

    chooseFile(sheet('october.csv', 'text/csv'));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Still working. The server is reading the file.',
    );
    await waitFor(() => expect(router.state.location.pathname).toBe('/imports/4'));
  });

  it('gives up on a cut upload after the wait and says where to look', async () => {
    POLL.every = 10;
    POLL.upTo = 60;
    server.use(http.post('/api/v1/imports/', () => HttpResponse.error()));
    renderApp('/imports');
    await screen.findByRole('table', { name: 'Imports' });

    chooseFile(sheet('october.csv', 'text/csv'));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The server may still be working, or the file was refused; check the batch list.',
    );
  });

  it('says the database is empty after a reset from the Demo data page', async () => {
    renderApp('/imports', { state: { reset: { employees: 15000 } } });

    expect(
      await screen.findByText('The database is empty. Import base-15000.xlsx to start.'),
    ).toBeInTheDocument();
  });
});
