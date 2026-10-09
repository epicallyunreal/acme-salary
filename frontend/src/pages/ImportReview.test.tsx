import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ImportBatch, ImportRow } from '../api/types';
import { setSession } from '../lib/auth';
import { tokens } from '../lib/theme';
import { POLL } from '../lib/poll';
import { expectClosed, expectFailed, expectPending, held } from '../test/busy';
import { approvedBatch, reviewBatch, reviewRows, rowsPage } from '../test/fixtures/imports';
import { renderApp } from '../test/render';
import { server } from '../test/setup';
import { expectEveryFieldLabelled, expectFocusCycle } from '../test/a11y';
import { SEARCH_DELAY_MS } from '../components/filters/FilterBar';

/** The review batch with its error row skipped: nothing stands in the way of approve. */
const READY: ImportBatch = { ...reviewBatch, error_rows: 0, skipped_rows: 2 };

/** 250 rows, 25 pages of 10, each a copy of a review row under a name of its own. */
const MANY_ROWS: ImportRow[] = Array.from({ length: 250 }, (_, index) => {
  const source = reviewRows[index % reviewRows.length];
  const name = `Person ${index + 1}`;
  return {
    ...source,
    id: 1000 + index,
    row_number: index + 2,
    full_name: name,
    raw: { ...source.raw, full_name: name },
  };
});

function rowOf(text: string): HTMLElement {
  const row = screen.getByText(text).closest('[role="row"]');
  if (!row) throw new Error(`no grid row holds ${text}`);
  return row as HTMLElement;
}

function summary() {
  return screen.getByLabelText('Batch summary');
}

/** The strip's one message slot (D75). */
function messages() {
  return screen.getByRole('group', { name: 'Batch messages' });
}

const BLOCKER = '1 row has errors. Skip it or fix the spreadsheet and upload again.';

describe('ImportReview', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('shows the summary, the ignored columns and every row with its messages', async () => {
    const user = userEvent.setup();
    renderApp('/imports/3');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'october-raises.xlsx' }),
    ).toBeInTheDocument();
    expect(summary()).toHaveTextContent('Total5Valid2Warning1Error1Skipped1No-op1');
    // The blocker first, then the ignored column, one at a time in the strip's slot (D75).
    expect(within(messages()).getByText(BLOCKER)).toBeInTheDocument();
    await user.click(within(messages()).getByRole('button', { name: 'Next message' }));
    expect(within(messages()).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    await screen.findByText('Ravi Iyer');
    const ravi = rowOf('Ravi Iyer');
    expect(within(ravi).getByText('error')).toBeInTheDocument();
    expect(within(ravi).getByText('revise')).toBeInTheDocument();
    expect(
      within(ravi).getByText('BASE must be a non-negative number, got -5000'),
    ).toBeInTheDocument();
    // The severity is said in words, not by colour alone.
    expect(within(ravi).getByText('Error:')).toBeInTheDocument();
    expect(within(rowOf('Mohan Khan')).getByText('Warning:')).toBeInTheDocument();
    const base = within(ravi).getByText('-5000');
    expect(base).toHaveAttribute('data-severity', 'error');
    await user.hover(base);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'BASE must be a non-negative number, got -5000',
    );
    expect(within(rowOf('Mohan Khan')).getByText('warning')).toBeInTheDocument();
    // A cell with nothing to say shows its full value on hover, as the sheet had it (D75).
    expect(within(ravi).getByText('Ravi Iyer')).toHaveAttribute('title', 'Ravi Iyer');
    // The action chip names a row that changes nothing as the strip counts it (D76).
    expect(within(rowOf('Lata Rao')).getByText('No-op')).toBeInTheDocument();
    expect(
      within(rowOf('No Code')).getByRole('button', { name: 'Unskip row 5' }),
    ).toBeInTheDocument();
  });

  it('stands its grid ten rows high whatever the window, 505 px (D75)', async () => {
    renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    // Ten rows, plus the grid's own sideways scrollbar while its columns scroll (D75).
    expect(getComputedStyle(document.querySelector('.MuiDataGrid-root') as Element).height).toBe(
      'calc(505px + var(--DataGrid-hasScrollX) * var(--DataGrid-scrollbarSize))',
    );
  });

  it('numbers its pages and jumps to the one typed, or the nearest there is, in the URL', async () => {
    const user = userEvent.setup();
    const asked: (string | null)[] = [];
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        asked.push(url.searchParams.get('page'));
        return HttpResponse.json(rowsPage(url, MANY_ROWS));
      }),
    );
    const { router } = renderApp('/imports/3?page=4');
    await screen.findByText('Person 31');

    const pager = screen.getByRole('navigation', { name: 'pagination navigation' });
    expect(
      within(pager)
        .getAllByRole('button')
        .map((button) => button.getAttribute('aria-label')),
    ).toEqual([
      'Go to previous page',
      'Go to page 1',
      'Go to page 2',
      'Go to page 3',
      'page 4',
      'Go to page 5',
      'Go to page 25',
      'Go to next page',
    ]);
    expect(within(pager).getByText('…')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Go to page'), '30{Enter}');

    await screen.findByText('Person 241');
    expect(router.state.location.search).toBe('?page=25');
    expect(asked).toEqual(['4', '25']);
  });

  it('numbers its pages for the rows per page the URL holds', async () => {
    const asked: [string | null, string | null][] = [];
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        asked.push([url.searchParams.get('page'), url.searchParams.get('page_size')]);
        return HttpResponse.json(rowsPage(url, MANY_ROWS));
      }),
    );
    renderApp('/imports/3?page_size=50&page=2');

    await screen.findByText('Person 51');
    expect(asked).toEqual([['2', '50']]);
    expect(screen.getByText('51–100 of 250')).toBeInTheDocument();
    const pager = screen.getByRole('navigation', { name: 'pagination navigation' });
    expect(within(pager).getByRole('button', { name: 'page 2' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(pager).getByRole('button', { name: 'Go to page 3' })).toBeInTheDocument();
  });

  it('filters the rows by status through the API and keeps the filter in the URL', async () => {
    const user = userEvent.setup();
    const asked: (string | null)[] = [];
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        asked.push(url.searchParams.get('status'));
        return HttpResponse.json(rowsPage(url));
      }),
    );
    const { router } = renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    await user.selectOptions(screen.getByLabelText('Status'), 'error');

    await waitFor(() => expect(screen.queryByText('Meera Iyer')).not.toBeInTheDocument());
    expect(screen.getByText('Ravi Iyer')).toBeInTheDocument();
    expect(asked.at(-1)).toBe('error');
    expect(router.state.location.search).toBe('?status=error');
  });

  it('searches the rows by code or name after a pause', async () => {
    const asked: (string | null)[] = [];
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        asked.push(url.searchParams.get('search'));
        return HttpResponse.json(rowsPage(url));
      }),
    );
    renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    // The pause is a fake timer that only advancing fires, so no edit can race it, and the real
    // clock is back before the request it releases is awaited.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const search = screen.getByLabelText('Search');
    fireEvent.change(search, { target: { value: 'HR-4' } });
    fireEvent.change(search, { target: { value: 'HR-41' } });
    expect(asked.filter(Boolean)).toEqual([]);
    act(() => vi.advanceTimersByTime(SEARCH_DELAY_MS));
    vi.useRealTimers();

    await waitFor(() => expect(screen.queryByText('Ravi Iyer')).not.toBeInTheDocument());
    expect(screen.getByText('Mohan Khan')).toBeInTheDocument();
    // Only the finished term was sent: the pause swallowed every keystroke before it.
    expect(asked.filter(Boolean)).toEqual(['HR-41']);
  });

  it('a search sent after its pause keeps the status chosen during it (D76)', async () => {
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) =>
        HttpResponse.json(rowsPage(new URL(request.url))),
      ),
    );
    const { router } = renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'HR-41' } });
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'error' } });
    act(() => vi.advanceTimersByTime(SEARCH_DELAY_MS));
    vi.useRealTimers();

    await waitFor(() => expect(router.state.location.search).toBe('?status=error&search=HR-41'));
  });

  it('opens a link to a page past the last on the last page, the URL replaced (D77)', async () => {
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        return Number(url.searchParams.get('page') ?? '1') > 25
          ? HttpResponse.json({ detail: 'Invalid page.' }, { status: 404 })
          : HttpResponse.json(rowsPage(url, MANY_ROWS));
      }),
    );
    const { router } = renderApp('/imports/3?page=900');

    await waitFor(() => expect(router.state.location.search).toBe('?page=25'));
    expect(router.state.historyAction).toBe('REPLACE');
    expect(await screen.findByText('Person 250')).toBeInTheDocument();
    expect(screen.queryByText(/Could not load/)).not.toBeInTheDocument();
  });

  it('says what to do when no row has the status chosen', async () => {
    renderApp('/imports/3?status=warning&search=nobody');

    expect(
      await screen.findByText('No rows with this status. Choose another status.'),
    ).toBeInTheDocument();
  });

  it('keeps Approve off while rows have errors, and says why', async () => {
    renderApp('/imports/3');

    const approve = await screen.findByRole('button', { name: 'Approve' });
    expect(approve).toBeDisabled();
    expect(within(messages()).getByText(BLOCKER)).toBeInTheDocument();
    expect(approve).toHaveAccessibleDescription(BLOCKER);
  });

  it('shows the blocker first and steps through three messages, 1/3, wrapping round (D75)', async () => {
    server.use(
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json({
          ...reviewBatch,
          warnings: ['Ignored unknown column: Remarks', 'Ignored unknown column: Notes'],
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/imports/3');
    const slot = await screen.findByRole('group', { name: 'Batch messages' });
    const approve = screen.getByRole('button', { name: 'Approve' });

    // The message and its place are read out as they change, not the buttons around them.
    expect(within(slot).getByText(BLOCKER).closest('[aria-live]')).toHaveAttribute(
      'aria-live',
      'polite',
    );
    expect(within(slot).getByText(BLOCKER)).toBeInTheDocument();
    expect(slot).toHaveStyle({ backgroundColor: tokens.status.warning.fill });
    expect(within(slot).getByText('1/3')).toBeInTheDocument();
    expect(within(slot).getByText('Message 1 of 3')).toBeInTheDocument();

    await user.click(within(slot).getByRole('button', { name: 'Next message' }));

    // One at a time: the next message takes the place of the last.
    expect(within(slot).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    expect(within(slot).queryByText(BLOCKER)).not.toBeInTheDocument();
    expect(within(slot).getByText('Message 2 of 3')).toBeInTheDocument();
    expect(slot).toHaveStyle({ backgroundColor: tokens.status.info.fill });
    // Approve still says why it is off while a warning shows.
    expect(approve).toHaveAccessibleDescription(BLOCKER);

    await user.click(within(slot).getByRole('button', { name: 'Next message' }));

    expect(within(slot).getByText('Ignored unknown column: Notes')).toBeInTheDocument();
    expect(within(slot).queryByText('Ignored unknown column: Remarks')).not.toBeInTheDocument();

    await user.click(within(slot).getByRole('button', { name: 'Next message' }));

    expect(within(slot).getByText(BLOCKER)).toBeInTheDocument();
    expect(within(slot).queryByText('Ignored unknown column: Notes')).not.toBeInTheDocument();

    await user.click(within(slot).getByRole('button', { name: 'Previous message' }));

    expect(within(slot).getByText('Ignored unknown column: Notes')).toBeInTheDocument();
    expect(within(slot).queryByText(BLOCKER)).not.toBeInTheDocument();
    expect(within(slot).getByText('3/3')).toBeInTheDocument();
  });

  it('starts again from the first message when the blocker goes, so none is skipped over', async () => {
    let skipped = false;
    const warnings = ['Ignored unknown column: Remarks', 'Ignored unknown column: Notes'];
    server.use(
      http.post('/api/v1/imports/3/rows/33/skip/', () => {
        skipped = true;
        return HttpResponse.json({ ...reviewRows[2], status: 'skipped' });
      }),
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json(skipped ? { ...READY, warnings } : { ...reviewBatch, warnings }),
      ),
    );
    const user = userEvent.setup();
    renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');
    await user.click(within(messages()).getByRole('button', { name: 'Next message' }));
    expect(within(messages()).getByText('Message 2 of 3')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Skip row 4' }));

    await waitFor(() => expect(within(messages()).getByText('Message 1 of 2')).toBeInTheDocument());
    expect(within(messages()).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
  });

  it('opens a link with 25 or 100 rows a page at 10, the size the grid stands (D75)', async () => {
    for (const size of ['25', '100']) {
      const asked: (string | null)[] = [];
      server.use(
        http.get('/api/v1/imports/3/rows/', ({ request }) => {
          const url = new URL(request.url);
          asked.push(url.searchParams.get('page_size'));
          return HttpResponse.json(rowsPage(url, MANY_ROWS));
        }),
      );
      const { unmount } = renderApp(`/imports/3?page_size=${size}`);

      await screen.findByText('1–10 of 250');
      expect(asked[0]).toBe('10');
      unmount();
    }
  });

  it('writes every count of an applied batch with its thousands separated', async () => {
    const big = {
      ...approvedBatch,
      total_rows: 2500,
      valid_rows: 2500,
      applied_rows: 2500,
      created_rows: 1250,
      updated_rows: 0,
      revised_rows: 1250,
    };
    server.use(http.get('/api/v1/imports/2/', () => HttpResponse.json(big)));
    renderApp('/imports/2');

    expect(
      await screen.findByText(
        /Applied 2,500 rows on .*: 1,250 created, 0 updated, 1,250 revised\./,
      ),
    ).toBeInTheDocument();
  });

  it('keeps the blocker and Show them out of the slot once the batch has left review', async () => {
    server.use(
      http.get('/api/v1/imports/2/', () =>
        HttpResponse.json({ ...approvedBatch, warnings: ['Ignored unknown column: Remarks'] }),
      ),
    );
    renderApp('/imports/2');

    const slot = await screen.findByRole('group', { name: 'Batch messages' });

    expect(within(slot).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    expect(within(slot).queryByText(/This batch is/)).not.toBeInTheDocument();
    expect(within(slot).queryByRole('button', { name: 'Show them' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).not.toHaveAttribute('aria-describedby');
  });

  it('gives a message its whole text on hover', async () => {
    renderApp('/imports/3');

    const text = await within(
      await screen.findByRole('group', { name: 'Batch messages' }),
    ).findByText(BLOCKER);

    expect(text).toHaveAttribute('title', BLOCKER);
  });

  it('shows one message alone, with nothing to step through', async () => {
    server.use(http.get('/api/v1/imports/3/', () => HttpResponse.json(READY)));
    renderApp('/imports/3');

    await screen.findByText('Ravi Iyer');
    const slot = messages();

    expect(within(slot).getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    expect(within(slot).queryByRole('button', { name: 'Next message' })).not.toBeInTheDocument();
    expect(within(slot).queryByText(/Message 1 of/)).not.toBeInTheDocument();
  });

  it('shows no slot when there is nothing to say', async () => {
    server.use(http.get('/api/v1/imports/3/', () => HttpResponse.json({ ...READY, warnings: [] })));
    renderApp('/imports/3');

    await screen.findByText('Ravi Iyer');

    expect(screen.queryByRole('group', { name: 'Batch messages' })).not.toBeInTheDocument();
  });

  it("the blocker's Show them sets the Status filter to Error", async () => {
    const asked: (string | null)[] = [];
    server.use(
      http.get('/api/v1/imports/3/rows/', ({ request }) => {
        const url = new URL(request.url);
        asked.push(url.searchParams.get('status'));
        return HttpResponse.json(rowsPage(url));
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    await user.click(within(messages()).getByRole('button', { name: 'Show them' }));

    await waitFor(() => expect(router.state.location.search).toBe('?status=error'));
    await waitFor(() => expect(asked.at(-1)).toBe('error'));
  });

  it('skips a row and refetches the summary, which turns Approve on', async () => {
    const user = userEvent.setup();
    let skipped = false;
    server.use(
      http.post('/api/v1/imports/3/rows/33/skip/', () => {
        skipped = true;
        return HttpResponse.json({ ...reviewRows[2], status: 'skipped' });
      }),
      http.get('/api/v1/imports/3/', () => HttpResponse.json(skipped ? READY : reviewBatch)),
      http.get('/api/v1/imports/3/rows/', ({ request }) =>
        HttpResponse.json(
          rowsPage(
            new URL(request.url),
            reviewRows.map((row) =>
              skipped && row.id === 33 ? { ...row, status: 'skipped' as const } : row,
            ),
          ),
        ),
      ),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Skip row 4' }));

    expect(await screen.findByRole('button', { name: 'Unskip row 4' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
    expect(summary()).toHaveTextContent('Error0Skipped2');
  });

  it('approves after confirming and says what was applied', async () => {
    const user = userEvent.setup();
    const applied: ImportBatch = {
      ...READY,
      status: 'approved',
      applied_rows: 2,
      created_rows: 1,
      revised_rows: 1,
      approved_at: '2026-10-07T09:30:00+00:00',
    };
    let approved = false;
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(approved ? applied : READY)),
      http.post('/api/v1/imports/3/approve/', () => {
        approved = true;
        return HttpResponse.json(applied);
      }),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Applied 2 rows: 1 created, 0 updated, 1 revised.',
    );
    expect(await screen.findByText(/Applied 2 rows on 7 Oct 2026/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip row 2' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('keeps waiting through a cut approve until the batch leaves review', async () => {
    const defaults = { ...POLL };
    POLL.every = 10;
    POLL.upTo = 2000;
    const user = userEvent.setup();
    let polls = 0;
    const done: ImportBatch = {
      ...READY,
      status: 'approved',
      applied_rows: 2,
      created_rows: 1,
      updated_rows: 0,
      revised_rows: 1,
      approved_at: '2026-10-07T09:30:00+00:00',
    };
    server.use(
      http.get('/api/v1/imports/3/', () => {
        polls += 1;
        return HttpResponse.json(polls >= 3 ? done : READY);
      }),
      http.post('/api/v1/imports/3/approve/', () => HttpResponse.error()),
    );
    renderApp('/imports/3');
    try {
      await user.click(await screen.findByRole('button', { name: 'Approve' }));
      const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
      await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

      expect(await screen.findByRole('status')).toHaveTextContent('Still working\u2026');
      expect(
        await screen.findByText('Applied 2 rows: 1 created, 0 updated, 1 revised.'),
      ).toBeInTheDocument();
      await expectClosed('Applying 2 rows\u2026');
      expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    } finally {
      Object.assign(POLL, defaults);
    }
  });

  it('gives up on a cut approve after the wait and says where to look', async () => {
    const defaults = { ...POLL };
    POLL.every = 10;
    POLL.upTo = 60;
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(READY)),
      http.post('/api/v1/imports/3/approve/', () => HttpResponse.error()),
    );
    renderApp('/imports/3');
    try {
      await user.click(await screen.findByRole('button', { name: 'Approve' }));
      const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
      await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

      await expectFailed(
        'Nothing was applied',
        'The server may still be working, or the approve was refused; open the batch again.',
      );
    } finally {
      Object.assign(POLL, defaults);
    }
  });

  it('says so when a cut approve ends with the batch failed', async () => {
    const defaults = { ...POLL };
    POLL.every = 10;
    POLL.upTo = 2000;
    const user = userEvent.setup();
    let polls = 0;
    const failed: ImportBatch = {
      ...READY,
      status: 'failed',
      error_summary: 'the server has logged the cause',
    };
    server.use(
      http.get('/api/v1/imports/3/', () => {
        polls += 1;
        return HttpResponse.json(polls >= 3 ? failed : READY);
      }),
      http.post('/api/v1/imports/3/approve/', () => HttpResponse.error()),
    );
    renderApp('/imports/3');
    try {
      await user.click(await screen.findByRole('button', { name: 'Approve' }));
      const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
      await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

      const failed = await screen.findByRole('dialog', { name: 'Nothing was applied' });
      expect(within(failed).getByRole('alert')).toHaveTextContent(
        'approve failed, the batch is marked failed',
      );
      expect(within(failed).getByRole('alert')).toHaveTextContent(
        'the server has logged the cause',
      );
    } finally {
      Object.assign(POLL, defaults);
    }
  });

  it('shows why an approve was refused, with the rows the re-check marked', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(READY)),
      http.post('/api/v1/imports/3/approve/', () =>
        HttpResponse.json(
          { detail: '1 row failed re-validation against current data', rows: [3] },
          { status: 409 },
        ),
      ),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    const failed = await screen.findByRole('dialog', { name: 'Nothing was applied' });
    const problems = within(failed).getByRole('alert');
    expect(problems).toHaveTextContent('1 row failed re-validation against current data');
    expect(problems).toHaveTextContent(
      'Row 3 is marked with the reason. Skip it or upload the sheet again.',
    );
    expect(within(failed).getByRole('button', { name: 'Close' })).toHaveFocus();
    expect(screen.queryByRole('dialog', { name: 'Approve october-raises.xlsx?' })).toBeNull();
  });

  it('applies behind the busy dialog, which nothing dismisses until the server answers', async () => {
    const user = userEvent.setup();
    const applied: ImportBatch = {
      ...READY,
      status: 'approved',
      applied_rows: 2,
      created_rows: 1,
      revised_rows: 1,
    };
    let approved = false;
    const { handler, release } = held(() => {
      approved = true;
      return HttpResponse.json(applied);
    });
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(approved ? applied : READY)),
      http.post('/api/v1/imports/3/approve/', handler),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    await expectPending('Applying 2 rows\u2026');
    expect(screen.getByRole('button', { name: 'Approve', hidden: true })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard', hidden: true })).toBeDisabled();
    release();
    await expectClosed('Applying 2 rows\u2026');
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Applied 2 rows: 1 created, 0 updated, 1 revised.',
    );
  });

  it('discards behind the busy dialog, and shows a refusal with Close', async () => {
    const user = userEvent.setup();
    const { handler, release } = held(() =>
      HttpResponse.json({ ...reviewBatch, status: 'discarded' }),
    );
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(reviewBatch)),
      http.post('/api/v1/imports/3/discard/', handler),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Discard' }));
    let dialog = await screen.findByRole('dialog', { name: 'Discard october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Discard batch' }));

    await expectPending('Discarding october-raises.xlsx\u2026');
    release();
    await expectClosed('Discarding october-raises.xlsx\u2026');
    expect(await screen.findByRole('status')).toHaveTextContent(
      'october-raises.xlsx discarded. Nothing in it was applied.',
    );

    server.use(
      http.post('/api/v1/imports/3/discard/', () =>
        HttpResponse.json({ detail: 'the batch is approved, not in review' }, { status: 409 }),
      ),
    );
    await user.click(await screen.findByRole('button', { name: 'Discard' }));
    dialog = await screen.findByRole('dialog', { name: 'Discard october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Discard batch' }));

    await expectFailed('Not discarded', 'the batch is approved, not in review');
  });

  it('discards after confirming, and nothing can be skipped after', async () => {
    const user = userEvent.setup();
    let discarded = false;
    server.use(
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json(discarded ? { ...reviewBatch, status: 'discarded' } : reviewBatch),
      ),
      http.post('/api/v1/imports/3/discard/', () => {
        discarded = true;
        return HttpResponse.json({ ...reviewBatch, status: 'discarded' });
      }),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Discard' }));
    const dialog = await screen.findByRole('dialog', { name: 'Discard october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Discard batch' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'october-raises.xlsx discarded. Nothing in it was applied.',
    );
    expect(
      await screen.findByText('This batch was discarded. Nothing in it was applied.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip row 2' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Discard' })).toBeDisabled();
  });

  it('shows what made a failed approve fail', async () => {
    server.use(
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json({
          ...reviewBatch,
          status: 'failed',
          error_summary: 'the server has logged the cause',
        }),
      ),
    );
    renderApp('/imports/3');

    expect(
      await screen.findByText(
        'The approve failed and nothing was applied: the server has logged the cause. Upload the sheet again to retry.',
      ),
    ).toBeInTheDocument();
  });

  it('says an unknown import does not exist', async () => {
    renderApp('/imports/999');

    expect(
      await screen.findByText('This import does not exist. Go back to the imports.'),
    ).toBeInTheDocument();
  });

  it('offers a retry when the import does not load, and the retry loads it', async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get('/api/v1/imports/3/', () =>
        failing ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(reviewBatch),
      ),
    );
    renderApp('/imports/3');

    expect(
      await screen.findByText('Could not load this import. Check your connection and try again.'),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'october-raises.xlsx' }),
    ).toBeInTheDocument();
  });

  it('says how many rows block the approve when there are several', async () => {
    server.use(
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json({ ...reviewBatch, valid_rows: 1, error_rows: 2 }),
      ),
    );
    renderApp('/imports/3');

    expect(
      await within(await screen.findByRole('group', { name: 'Batch messages' })).findByText(
        '2 rows have errors. Skip them or fix the spreadsheet and upload again.',
      ),
    ).toBeInTheDocument();
  });

  it('unskipping an error row turns Approve off again', async () => {
    const user = userEvent.setup();
    let unskipped = false;
    const skippedError = { ...reviewRows[2], status: 'skipped' as const };
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(unskipped ? reviewBatch : READY)),
      http.get('/api/v1/imports/3/rows/', ({ request }) =>
        HttpResponse.json(
          rowsPage(
            new URL(request.url),
            reviewRows.map((row) => (row.id === 33 && !unskipped ? skippedError : row)),
          ),
        ),
      ),
      http.post('/api/v1/imports/3/rows/33/unskip/', () => {
        unskipped = true;
        return HttpResponse.json(reviewRows[2]);
      }),
    );
    renderApp('/imports/3');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());

    await user.click(await screen.findByRole('button', { name: 'Unskip row 4' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled());
    expect(await screen.findByRole('button', { name: 'Skip row 4' })).toBeInTheDocument();
  });

  it('refreshes the rows and the summary after the re-check refuses an approve', async () => {
    const user = userEvent.setup();
    let refused = false;
    const marked = {
      ...reviewRows[1],
      status: 'error' as const,
      validation_status: 'error' as const,
      messages: [
        {
          field: 'effective_from',
          severity: 'error' as const,
          message: 'effective_from must be after 2026-12-01 (latest record)',
        },
      ],
    };
    server.use(
      http.get('/api/v1/imports/3/', () =>
        HttpResponse.json(refused ? { ...READY, warning_rows: 0, error_rows: 1 } : READY),
      ),
      http.get('/api/v1/imports/3/rows/', ({ request }) =>
        HttpResponse.json(
          rowsPage(
            new URL(request.url),
            reviewRows.map((row) => (refused && row.id === 32 ? marked : row)),
          ),
        ),
      ),
      http.post('/api/v1/imports/3/approve/', () => {
        refused = true;
        return HttpResponse.json(
          { detail: '1 row failed re-validation against current data', rows: [3] },
          { status: 409 },
        );
      }),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));
    const failed = await screen.findByRole('dialog', { name: 'Nothing was applied' });
    await user.click(within(failed).getByRole('button', { name: 'Close' }));
    await expectClosed('Nothing was applied');

    expect(
      await screen.findByText(/effective_from must be after 2026-12-01 \(latest record\)/),
    ).toBeInTheDocument();
    expect(summary()).toHaveTextContent('Error1');
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it("shows a failed approve's summary in the dialog", async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/imports/3/', () => HttpResponse.json(READY)),
      http.post('/api/v1/imports/3/approve/', () =>
        HttpResponse.json(
          {
            detail: 'approve failed, the batch is marked failed',
            error_summary: 'the server has logged the cause',
          },
          { status: 409 },
        ),
      ),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    const dialog = await screen.findByRole('dialog', { name: 'Approve october-raises.xlsx?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    const failed = await screen.findByRole('dialog', { name: 'Nothing was applied' });
    const problems = within(failed).getByRole('alert');
    expect(problems).toHaveTextContent('approve failed, the batch is marked failed');
    expect(problems).toHaveTextContent('the server has logged the cause');
  });

  it('says why a skip did not take, as an error', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/imports/3/rows/33/skip/', () =>
        HttpResponse.json({ detail: 'the batch is approved, not in review' }, { status: 409 }),
      ),
    );
    renderApp('/imports/3');

    await user.click(await screen.findByRole('button', { name: 'Skip row 4' }));

    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent(
      'The row did not change: the batch is approved, not in review.',
    );
    expect(notice.className).toMatch(/Error/);
  });
  it.each([
    ['Approve', 'Approve october-raises.xlsx?'],
    ['Discard', 'Discard october-raises.xlsx?'],
  ])('%s opens a dialog that takes focus and hands it back on Escape', async (trigger, title) => {
    const user = userEvent.setup();
    server.use(http.get('/api/v1/imports/3/', () => HttpResponse.json(READY)));
    renderApp('/imports/3');
    const button = await screen.findByRole('button', { name: trigger });

    await expectFocusCycle(user, button, title);
  });

  it('labels the filter and the search', async () => {
    renderApp('/imports/3');
    await screen.findByText('Ravi Iyer');

    expectEveryFieldLabelled();
  });
});
