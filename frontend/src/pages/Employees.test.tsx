import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../lib/auth';
import { employeePage } from '../test/fixtures/employees';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

/** Replaces the directory handler with one that records every query string it receives. */
function recordRequests() {
  const seen: URLSearchParams[] = [];
  server.use(
    http.get('/api/v1/employees/', ({ request }) => {
      seen.push(new URL(request.url).searchParams);
      return HttpResponse.json(employeePage);
    }),
  );
  return seen;
}

async function rowsShown() {
  await screen.findByText('Asha Rao');
  return screen.getAllByRole('row').slice(1); // the first row is the header
}

describe('Employees', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('renders the fixture rows with money as codes and status as chips', async () => {
    renderApp('/employees');

    const rows = await rowsShown();

    expect(rows).toHaveLength(4);
    expect(screen.getByText('4 employees')).toBeInTheDocument();
    const asha = rows[0];
    expect(within(asha).getByText('ACME-000001')).toBeInTheDocument();
    expect(within(asha).getByText('INR 1,450,000')).toBeInTheDocument();
    expect(within(asha).getByText('USD 17,400')).toBeInTheDocument();
    expect(within(asha).getByText('active')).toBeInTheDocument();
    expect(within(asha).getByText('current')).toBeInTheDocument();
    const chloe = rows[2];
    expect(within(chloe).getByText('exited')).toBeInTheDocument();
    expect(within(chloe).getByText('exited 30 Jun 2026')).toBeInTheDocument();
    expect(within(chloe).getByText('GBP 80,000')).toBeInTheDocument();
    expect(screen.queryByText('asha@acme.example')).not.toBeInTheDocument();
  });

  it('sends the URL state to the API and a filter change goes back to page 1', async () => {
    const seen = recordRequests();
    renderApp('/employees?page=2&ordering=-gross&level=3');
    const user = userEvent.setup();
    await rowsShown();

    expect(seen[0].get('page')).toBe('2');
    expect(seen[0].get('ordering')).toBe('-gross');
    expect(seen[0].get('level')).toBe('3');
    expect(seen[0].has('currency')).toBe(false);

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('IN'));
    expect(seen.at(-1)?.get('page')).toBe('1');
    expect(seen.at(-1)?.get('ordering')).toBe('-gross');
    expect(seen.at(-1)?.get('level')).toBe('3');
  });

  it('offers the local currency only for a single country', async () => {
    const seen = recordRequests();
    renderApp('/employees?country=IN');
    const user = userEvent.setup();
    await rowsShown();

    await user.click(screen.getByLabelText('Currency'));
    await user.click(await screen.findByRole('option', { name: 'Local' }));

    await waitFor(() => expect(seen.at(-1)?.get('currency')).toBe('local'));
    expect(screen.getByText('Gross (local currency)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'United States' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('IN,US'));
    expect(seen.at(-1)?.has('currency')).toBe(false);
  });

  it('searches after a pause and sorts by the reporting gross', async () => {
    const seen = recordRequests();
    renderApp('/employees');
    const user = userEvent.setup();
    await rowsShown();

    await user.type(screen.getByLabelText('Search'), 'rao');
    await waitFor(() => expect(seen.at(-1)?.get('search')).toBe('rao'));

    await user.click(screen.getByRole('columnheader', { name: 'Gross (USD)' }));
    await waitFor(() => expect(seen.at(-1)?.get('ordering')).toBe('gross'));
    expect(seen.at(-1)?.get('search')).toBe('rao');
  });

  it('opens an employee on row click', async () => {
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    const rows = await rowsShown();

    await user.click(within(rows[1]).getByText('Ben Carter'));

    await waitFor(() => expect(router.state.location.pathname).toBe('/employees/2'));
  });

  it('shows the error state with a retry that refetches', async () => {
    let calls = 0;
    server.use(
      http.get('/api/v1/employees/', () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(employeePage);
      }),
    );
    renderApp('/employees');
    const user = userEvent.setup();

    await screen.findByText('Could not load employees. Check your connection and try again.');
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    await screen.findByText('Asha Rao');
  });

  it('says what to do when the filters match nothing', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderApp('/employees?search=nobody');

    await screen.findByText(
      'No employees match these filters. Clear a filter or change the search.',
    );
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });
});
