import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import type { ImportBatch } from '../api/types';
import { setSession } from '../lib/auth';
import { reviewBatch, reviewRows, rowsPage } from '../test/fixtures/imports';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

/** The review batch with its error row skipped: nothing stands in the way of approve. */
const READY: ImportBatch = { ...reviewBatch, error_rows: 0, skipped_rows: 2 };

function rowOf(text: string): HTMLElement {
  const row = screen.getByText(text).closest('[role="row"]');
  if (!row) throw new Error(`no grid row holds ${text}`);
  return row as HTMLElement;
}

function summary() {
  return screen.getByLabelText('Batch summary');
}

describe('ImportReview', () => {
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
    expect(screen.getByText('Ignored unknown column: Remarks')).toBeInTheDocument();
    await screen.findByText('Ravi Iyer');
    const ravi = rowOf('Ravi Iyer');
    expect(within(ravi).getByText('error')).toBeInTheDocument();
    expect(within(ravi).getByText('revise')).toBeInTheDocument();
    expect(
      within(ravi).getByText('BASE must be a non-negative number, got -5000'),
    ).toBeInTheDocument();
    const base = within(ravi).getByText('-5000');
    expect(base).toHaveAttribute('data-severity', 'error');
    await user.hover(base);
    expect(await screen.findByRole('tooltip')).toHaveTextContent(
      'BASE must be a non-negative number, got -5000',
    );
    expect(within(rowOf('Mohan Khan')).getByText('warning')).toBeInTheDocument();
    expect(within(rowOf('Lata Rao')).getByText('noop')).toBeInTheDocument();
    expect(
      within(rowOf('No Code')).getByRole('button', { name: 'Unskip row 5' }),
    ).toBeInTheDocument();
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
    const user = userEvent.setup();
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

    await user.type(screen.getByLabelText('Search'), 'HR-41');

    await waitFor(() => expect(screen.queryByText('Ravi Iyer')).not.toBeInTheDocument());
    expect(screen.getByText('Mohan Khan')).toBeInTheDocument();
    expect(asked.at(-1)).toBe('HR-41');
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
    const reason = '1 row has errors. Skip it or fix the spreadsheet and upload again.';
    expect(approve).toBeDisabled();
    expect(screen.getByText(reason)).toBeInTheDocument();
    expect(approve).toHaveAccessibleDescription(reason);
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
    const dialog = await screen.findByRole('dialog', { name: 'Apply 2 rows?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Applied 2 rows: 1 created, 0 updated, 1 revised.',
    );
    expect(await screen.findByText(/Applied 2 rows on 7 Oct 2026/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Skip row 2' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
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
    const dialog = await screen.findByRole('dialog', { name: 'Apply 2 rows?' });
    await user.click(within(dialog).getByRole('button', { name: 'Approve and apply' }));

    const problems = await within(dialog).findByRole('alert');
    expect(problems).toHaveTextContent('Nothing was applied');
    expect(problems).toHaveTextContent('1 row failed re-validation against current data');
    expect(problems).toHaveTextContent(
      'Row 3 is marked with the reason. Skip it or upload the sheet again.',
    );
    expect(problems).toHaveFocus();
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
          error_summary: 'OSError: disk full',
        }),
      ),
    );
    renderApp('/imports/3');

    expect(
      await screen.findByText(
        'The approve failed and nothing was applied: OSError: disk full. Upload the sheet again to retry.',
      ),
    ).toBeInTheDocument();
  });

  it('says an unknown import does not exist', async () => {
    renderApp('/imports/999');

    expect(
      await screen.findByText('This import does not exist. Go back to the imports.'),
    ).toBeInTheDocument();
  });

  it('offers a retry when the import does not load', async () => {
    server.use(http.get('/api/v1/imports/3/', () => HttpResponse.json({}, { status: 500 })));
    renderApp('/imports/3');

    expect(
      await screen.findByText('Could not load this import. Check your connection and try again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
