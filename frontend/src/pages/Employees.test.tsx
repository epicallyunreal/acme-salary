import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../lib/auth';
import { employeePage, employees } from '../test/fixtures/employees';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

/** Sixty rows, so the directory has three pages of 25; every row is a copy of the fixture. */
function sixtyRows(params: URLSearchParams) {
  const page = Number(params.get('page') ?? '1');
  const pageSize = Number(params.get('page_size') ?? '25');
  const results = Array.from({ length: 60 }, (_, index) => ({
    ...employees[index % employees.length],
    id: index + 1,
    employee_code: `ACME-${index + 1}`,
  })).slice((page - 1) * pageSize, page * pageSize);
  return {
    count: 60,
    next: page * pageSize < 60 ? 'next' : null,
    previous: page > 1 ? 'prev' : null,
    results,
  };
}

/** Replaces the directory handler with one that records every query string it receives. */
function recordRequests({ rows = 4 } = {}) {
  const seen: URLSearchParams[] = [];
  server.use(
    http.get('/api/v1/employees/', ({ request }) => {
      const params = new URL(request.url).searchParams;
      seen.push(params);
      return HttpResponse.json(rows === 60 ? sixtyRows(params) : employeePage);
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
    expect(within(asha).getByText('ACME-1')).toBeInTheDocument();
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

  it('renders an employee with no live record, with empty pay cells', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({
          ...employeePage,
          results: employees.map((row) =>
            row.id === 2 ? { ...row, status: 'exited', last_date: '2026-09-30', shown: null } : row,
          ),
        }),
      ),
    );
    renderApp('/employees');

    const ben = (await rowsShown())[1];

    expect(within(ben).getByText('Ben Carter')).toBeInTheDocument();
    expect(within(ben).getByText('exited')).toBeInTheDocument();
    expect(within(ben).getByText('no record')).toBeInTheDocument();
    expect(within(ben).queryByText(/USD/)).not.toBeInTheDocument();
  });

  it('keeps the Status label above Any instead of over it', async () => {
    renderApp('/employees');

    await screen.findAllByText('Asha Rao');
    const status = screen.getByRole('combobox', { name: 'Status' });
    expect(status).toHaveTextContent('Any');
    expect(screen.getByText('Status', { selector: 'label' })).toHaveAttribute(
      'data-shrink',
      'true',
    );
  });

  it('keeps a deep link on its page and pages forward with the filters kept', async () => {
    const seen = recordRequests({ rows: 60 });
    const { router } = renderApp('/employees?page=2&country=IN');
    const user = userEvent.setup();

    await screen.findByText('ACME-26');
    expect(seen.map((params) => params.get('page'))).toEqual(['2']);
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      page: '2',
      country: 'IN',
    });

    await user.click(screen.getByRole('button', { name: /next page/i }));

    await screen.findByText('ACME-51');
    expect(seen.at(-1)?.get('page')).toBe('3');
    expect(seen.at(-1)?.get('country')).toBe('IN');
    expect(seen.map((params) => params.get('page'))).toEqual(['2', '3']);
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      page: '3',
      country: 'IN',
    });
  });

  it('sends the URL state to the API and a filter change goes back to page 1', async () => {
    const seen = recordRequests({ rows: 60 });
    renderApp('/employees?page=2&ordering=-gross&level=3');
    const user = userEvent.setup();
    await screen.findByText('ACME-26');

    expect(seen).toHaveLength(1);
    expect(seen[0].get('page')).toBe('2');
    expect(seen[0].get('ordering')).toBe('-gross');
    expect(seen[0].get('level')).toBe('3');
    expect(seen[0].has('currency')).toBe(false);

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('IN'));
    expect(seen).toHaveLength(2);
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
    expect(await screen.findByText('Gross (INR)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'United States' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('IN,US'));
    expect(seen.at(-1)?.has('currency')).toBe(false);
    expect(screen.getByText('Gross (USD)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Currency'));
    expect(await screen.findByRole('option', { name: 'EUR' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Local' })).not.toBeInTheDocument();
  });

  it('keeps local through a switch from India to Germany, and drops it for two countries', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    renderApp('/employees?country=IN&currency=local');
    await rowsShown();
    expect(await screen.findByText('Gross (INR)')).toBeInTheDocument();

    // India to Germany in one visit to the menu: still one country, so local stays.
    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.click(screen.getByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('DE'));
    expect(seen.at(-1)?.get('currency')).toBe('local');
    expect(await screen.findByText('Gross (EUR)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.get('country')).toBe('DE,IN'));
    expect(seen.at(-1)?.has('currency')).toBe(false);
    expect(await screen.findByText('Gross (USD)')).toBeInTheDocument();
  });

  it('drops local when no country is left', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    renderApp('/employees?country=DE&currency=local');
    await rowsShown();
    expect(await screen.findByText('Gross (EUR)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.at(-1)?.has('country')).toBe(false));
    expect(seen.at(-1)?.has('currency')).toBe(false);
    expect(await screen.findByText('Gross (USD)')).toBeInTheDocument();
  });

  it('searches after a pause and sorts by the reporting gross', async () => {
    const seen = recordRequests();
    renderApp('/employees');
    const user = userEvent.setup();
    await rowsShown();

    await user.type(screen.getByLabelText('Search'), 'rao');
    await waitFor(() => expect(seen.at(-1)?.get('search')).toBe('rao'));
    // One request for the whole word, not one per keystroke.
    expect(seen.map((params) => params.get('search'))).toEqual([null, 'rao']);

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

  it('says what to do when there is no data at all', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({ count: 0, next: null, previous: null, results: [] }),
      ),
    );
    renderApp('/employees');

    await screen.findByText('No employees yet. Import a spreadsheet or add an employee.');
    expect(screen.queryByRole('button', { name: 'Clear filters' })).not.toBeInTheDocument();
  });

  it('sends the user to login, with the way back, when the session cannot be refreshed', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({ detail: 'expired' }, { status: 401 }),
      ),
      http.post('/api/v1/auth/refresh/', () =>
        HttpResponse.json({ detail: 'Token is blacklisted' }, { status: 401 }),
      ),
    );
    const { router } = renderApp('/employees?country=IN');

    await screen.findByRole('heading', { name: 'ACME Salary' });
    const { pathname, search } = router.state.location;
    expect(pathname).toBe('/login');
    expect(new URLSearchParams(search).get('next')).toBe('/employees?country=IN');
  });
});
