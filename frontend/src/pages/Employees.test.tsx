import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { employeePage, employees } from '../test/fixtures/employees';
import { renderApp } from '../test/render';
import { server } from '../test/setup';
import { SEARCH_DELAY_MS } from '../components/filters/FilterBar';
import { expectEveryFieldLabelled } from '../test/a11y';

/** Sixty rows, so the directory has six pages of 10; every row is a copy of the fixture. */
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

/** 10,000 employees, as many pages as the page size makes, each row a copy of the fixture. */
function tenThousandRows(params: URLSearchParams) {
  const page = Number(params.get('page') ?? '1');
  const pageSize = Number(params.get('page_size') ?? '25');
  const first = (page - 1) * pageSize;
  return {
    count: 10000,
    next: first + pageSize < 10000 ? 'next' : null,
    previous: page > 1 ? 'prev' : null,
    results: Array.from({ length: Math.min(pageSize, 10000 - first) }, (_, index) => ({
      ...employees[index % employees.length],
      id: first + index + 1,
      employee_code: `ACME-${first + index + 1}`,
    })),
  };
}

/** Replaces the directory handler with one that records every query string it receives. */
function recordRequests({ rows = 4 } = {}) {
  const seen: URLSearchParams[] = [];
  server.use(
    http.get('/api/v1/employees/', ({ request }) => {
      const params = new URL(request.url).searchParams;
      seen.push(params);
      if (rows === 10000) return HttpResponse.json(tenThousandRows(params));
      return HttpResponse.json(rows === 60 ? sixtyRows(params) : employeePage);
    }),
  );
  return seen;
}

/** The labels of the pager's buttons, in order. */
function pageButtons(): (string | null)[] {
  const pager = screen.getByRole('navigation', { name: 'pagination navigation' });
  return within(pager)
    .getAllByRole('button')
    .map((button) => button.getAttribute('aria-label'));
}

/** A column header by its title. A sortable one's name ends with its sort button's label. */
function columnHeader(title: string) {
  const escaped = title.replace(/[()]/g, '\\$&');
  return screen.getByRole('columnheader', { name: new RegExp(`^${escaped}( Sort)?$`) });
}

async function rowsShown() {
  await screen.findByText('Asha Rao');
  return screen.getAllByRole('row').slice(1); // the first row is the header
}

describe('Employees', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

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
    expect(within(asha).getByText('USD 17,400')).toBeInTheDocument();
    expect(within(asha).getByText('active')).toBeInTheDocument();
    const chloe = rows[2];
    expect(within(chloe).getByText('exited')).toBeInTheDocument();
    expect(within(chloe).getByText('USD 107,600')).toBeInTheDocument();
    // A name or a department the column cuts short shows in full on hover (D75).
    expect(within(asha).getByText('Asha Rao')).toHaveAttribute('title', 'Asha Rao');
    expect(within(asha).getByText('Engineering')).toHaveAttribute('title', 'Engineering');
  });

  it('stands its grid ten rows high whatever the window, 505 px (D75)', async () => {
    renderApp('/employees');
    await rowsShown();

    // Ten rows, plus the grid's own sideways scrollbar while its columns scroll (D75).
    expect(getComputedStyle(document.querySelector('.MuiDataGrid-root') as Element).height).toBe(
      'calc(505px + var(--DataGrid-hasScrollX) * var(--DataGrid-scrollbarSize))',
    );
  });

  it('shades every second row so rows read apart (D75)', async () => {
    renderApp('/employees');

    const rows = await rowsShown();

    expect(rows.map((row) => row.classList.contains('odd'))).toEqual([false, true, false, true]);
    // On the page background, the theme's variable, so a lost rule fails here and not only a lost
    // class.
    expect(getComputedStyle(rows[1]).backgroundColor).toBe('var(--mui-palette-background-default)');
    expect(getComputedStyle(rows[0]).backgroundColor).toBe('rgba(0, 0, 0, 0)');
  });

  it('shows by default the columns a 1280 px window has room for, the rest in the chooser', async () => {
    renderApp('/employees');
    await rowsShown();

    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Edit',
      'Code',
      'Name',
      'Department',
      'Country',
      'Level',
      'Status',
      'Gross (USD)',
      'Joined',
    ]);
    expect(screen.queryByText('INR 1,450,000')).not.toBeInTheDocument();
    expect(screen.queryByText('current')).not.toBeInTheDocument();
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
    expect(within(ben).queryByText(/USD/)).not.toBeInTheDocument();
  });

  it('opens on Active, with Any one click away and Clear filters back to Active', async () => {
    const seen = recordRequests();
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    await rowsShown();
    const status = screen.getByRole('combobox', { name: 'Status' });

    expect(status).toHaveTextContent('Active');
    expect(screen.getByText('Status', { selector: 'label' })).toHaveAttribute(
      'data-shrink',
      'true',
    );
    expect(seen[0].has('status')).toBe(false);

    await user.click(status);
    await user.click(await screen.findByRole('option', { name: 'Any' }));

    await waitFor(() => expect(seen.at(-1)?.get('status')).toBe('any'));
    expect(router.state.location.search).toBe('?status=any');

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));

    await waitFor(() => expect(router.state.location.search).toBe(''));
    expect(screen.getByRole('combobox', { name: 'Status' })).toHaveTextContent('Active');
  });

  it('keeps a deep link on its page and pages forward with the filters kept', async () => {
    const seen = recordRequests({ rows: 60 });
    const { router } = renderApp('/employees?page=2&country=IN');
    const user = userEvent.setup();

    await screen.findByText('ACME-11');
    expect(seen.map((params) => params.get('page'))).toEqual(['2']);
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      page: '2',
      country: 'IN',
    });

    await user.click(screen.getByRole('button', { name: /next page/i }));

    await screen.findByText('ACME-21');
    expect(seen.at(-1)?.get('page')).toBe('3');
    expect(seen.at(-1)?.get('country')).toBe('IN');
    expect(seen.map((params) => params.get('page'))).toEqual(['2', '3']);
    expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
      page: '3',
      country: 'IN',
    });
  });

  it('numbers the pages: the first, the last, and the current one with its neighbours', async () => {
    recordRequests({ rows: 10000 });
    const user = userEvent.setup();
    const { router } = renderApp('/employees?page=5');

    await screen.findByText('ACME-41');
    expect(screen.getByText('41–50 of 10,000')).toBeInTheDocument();
    expect(pageButtons()).toEqual([
      'Go to previous page',
      'Go to page 1',
      'Go to page 4',
      'page 5',
      'Go to page 6',
      'Go to page 1000',
      'Go to next page',
    ]);
    expect(screen.getByRole('button', { name: 'page 5' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getAllByText('…')).toHaveLength(2);

    await user.click(screen.getByRole('button', { name: 'Go to page 1000' }));

    await screen.findByText('ACME-9991');
    expect(router.state.location.search).toBe('?page=1000');
    // At either end the pager shows more neighbours, so it keeps its width.
    expect(pageButtons()).toEqual([
      'Go to previous page',
      'Go to page 1',
      'Go to page 996',
      'Go to page 997',
      'Go to page 998',
      'Go to page 999',
      'page 1000',
      'Go to next page',
    ]);
    expect(screen.getByRole('button', { name: 'Go to next page' })).toBeDisabled();
  });

  it('jumps to the page typed on Enter, or the nearest there is', async () => {
    const seen = recordRequests({ rows: 10000 });
    const user = userEvent.setup();
    const { router } = renderApp('/employees');
    await screen.findByText('ACME-1');

    await user.type(screen.getByLabelText('Go to page'), '37{Enter}');

    await screen.findByText('ACME-361');
    expect(router.state.location.search).toBe('?page=37');
    expect(seen.at(-1)?.get('page')).toBe('37');
    expect(screen.getByLabelText('Go to page')).toHaveValue(null);

    await user.type(screen.getByLabelText('Go to page'), '1999{Enter}');

    await screen.findByText('ACME-9991');
    expect(router.state.location.search).toBe('?page=1000');

    await user.type(screen.getByLabelText('Go to page'), '0{Enter}');

    await screen.findByText('ACME-1');
    expect(router.state.location.search).toBe('');
  });

  it('an empty directory still shows page 1, and Go to page with nothing typed stays put', async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get('/api/v1/employees/', ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json({ count: 0, next: null, previous: null, results: [] });
      }),
    );
    const user = userEvent.setup();
    const { router } = renderApp('/employees');

    expect(
      await screen.findByText('No employees yet. Import a spreadsheet or add an employee.'),
    ).toBeInTheDocument();
    expect(pageButtons()).toEqual(['Go to previous page', 'page 1', 'Go to next page']);

    await user.type(screen.getByLabelText('Go to page'), '{Enter}');

    expect(router.state.location.search).toBe('');
    expect(seen).toHaveLength(1);
  });

  it('numbers the pages for the rows per page the URL holds', async () => {
    // jsdom applies no media query, so MUI X keeps its Rows per page select hidden here, as on a
    // phone. The size it sets is read from the URL like the page.
    const seen = recordRequests({ rows: 10000 });
    renderApp('/employees?page_size=50&page=2');

    await screen.findByText('ACME-51');
    expect([seen[0].get('page'), seen[0].get('page_size')]).toEqual(['2', '50']);
    expect(screen.getByText('51–100 of 10,000')).toBeInTheDocument();
    expect(pageButtons()).toContain('Go to page 200');
    expect(pageButtons()).not.toContain('Go to page 1000');
  });

  it('opens a link with 25 or 100 rows a page at 10, the size the grid stands (D75)', async () => {
    for (const size of ['25', '100']) {
      const seen = recordRequests({ rows: 10000 });
      const { unmount } = renderApp(`/employees?page_size=${size}`);

      await screen.findByText('1–10 of 10,000');
      expect(seen[0].get('page_size')).toBe('10');
      unmount();
    }
  });

  it('sends the URL state to the API and a filter change goes back to page 1', async () => {
    const seen = recordRequests({ rows: 60 });
    renderApp('/employees?page=2&ordering=-gross&level=3');
    const user = userEvent.setup();
    await screen.findByText('ACME-11');

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

    // The pause is a fake timer that only advancing fires, so no edit can race it, and the real
    // clock is back before the request it releases is awaited.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const search = screen.getByLabelText('Search');
    fireEvent.change(search, { target: { value: 'ra' } });
    fireEvent.change(search, { target: { value: 'rao' } });
    expect(seen.map((params) => params.get('search'))).toEqual([null]);
    act(() => vi.advanceTimersByTime(SEARCH_DELAY_MS));
    vi.useRealTimers();
    await waitFor(() => expect(seen.at(-1)?.get('search')).toBe('rao'));
    // One request for the whole word, not one per keystroke.
    expect(seen.map((params) => params.get('search'))).toEqual([null, 'rao']);

    await user.click(columnHeader('Gross (USD)'));
    await waitFor(() => expect(seen.at(-1)?.get('ordering')).toBe('gross'));
    expect(seen.at(-1)?.get('search')).toBe('rao');
  });

  it('opens an employee from the pencil, named and titled for them', async () => {
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    await rowsShown();
    const edit = screen.getByRole('link', { name: 'Edit Ben Carter' });

    expect(edit).toHaveAttribute('href', '/employees/2');
    await user.hover(edit);
    expect(await screen.findByRole('tooltip', { name: 'Edit Ben Carter' })).toBeInTheDocument();
    await user.click(edit);

    await waitFor(() => expect(router.state.location.pathname).toBe('/employees/2'));
  });

  it('marks each sortable column with an icon at rest and the sorted one with its arrow', async () => {
    renderApp('/employees?ordering=-gross');
    await rowsShown();
    const header = columnHeader;

    expect(within(header('Gross (USD)')).getByTestId('ArrowDownwardIcon')).toBeInTheDocument();
    for (const name of ['Code', 'Name', 'Department', 'Country', 'Level', 'Joined']) {
      expect(within(header(name)).getByTestId('SwapVertIcon')).toBeInTheDocument();
    }
    for (const name of ['Edit', 'Status']) {
      expect(within(header(name)).queryByRole('button', { name: 'Sort' })).not.toBeInTheDocument();
      expect(within(header(name)).queryByTestId('SwapVertIcon')).not.toBeInTheDocument();
    }
  });

  it('sorts by Code ascending by default, leaving it out of the URL and the request', async () => {
    const seen = recordRequests();
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    await rowsShown();

    expect(within(columnHeader('Code')).getByTestId('ArrowUpwardIcon')).toBeInTheDocument();
    expect(columnHeader('Code')).toHaveAttribute('aria-sort', 'ascending');
    expect(router.state.location.search).toBe('');
    expect(seen[0].has('ordering')).toBe(false);

    await user.click(columnHeader('Code'));

    await waitFor(() => expect(seen.at(-1)?.get('ordering')).toBe('-employee_code'));
    expect(router.state.location.search).toBe('?ordering=-employee_code');
  });

  it.each([
    ['a search in the link', '/employees?search=asha&country=IN', 'ashar'],
    ['no search before', '/employees?country=IN', 'rao'],
  ])(
    'a search typed but not yet sent is dropped by Clear filters, with %s (D76)',
    async (_, url, typed) => {
      recordRequests();
      const { router } = renderApp(url);
      await rowsShown();

      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      fireEvent.change(screen.getByLabelText('Search'), { target: { value: typed } });
      // Clear within the pause, the field never left.
      fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
      act(() => vi.advanceTimersByTime(SEARCH_DELAY_MS));
      vi.useRealTimers();

      await rowsShown();
      expect(router.state.location.search).toBe('');
      expect(screen.getByLabelText('Search')).toHaveValue('');
    },
  );

  it('clears the filters and the search but keeps the sort and the page size', async () => {
    recordRequests({ rows: 60 });
    const { router } = renderApp(
      '/employees?country=IN&search=rao&ordering=-gross&page_size=50&page=2',
    );
    const user = userEvent.setup();
    await screen.findByText('ACME-51');

    await user.click(screen.getByRole('button', { name: 'Clear filters' }));

    await waitFor(() => expect(router.state.location.search).toBe('?page_size=50&ordering=-gross'));
    expect(screen.getByLabelText('Search')).toHaveValue('');
  });

  it('opens nothing from a click on the rest of the row', async () => {
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    const rows = await rowsShown();

    await user.click(within(rows[1]).getByText('Ben Carter'));

    expect(router.state.location.pathname).toBe('/employees');
  });

  it("reaches the pencil by keyboard through the grid's cell focus", async () => {
    const { router } = renderApp('/employees');
    const user = userEvent.setup();
    const rows = await rowsShown();

    await user.click(within(rows[1]).getByText('ACME-2'));
    await user.keyboard('{ArrowLeft}');

    const edit = screen.getByRole('link', { name: 'Edit Ben Carter' });
    await waitFor(() => expect(edit).toHaveFocus());
    await user.keyboard('{Enter}');
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

  it("shows a filter the API refuses in the API's words on that field, the grid kept", async () => {
    server.use(
      http.get('/api/v1/employees/', ({ request }) => {
        const titles = new URL(request.url).searchParams.get('designation')?.split(',') ?? [];
        return titles.length > 20
          ? HttpResponse.json(
              { designation: ['designation accepts at most 20 titles'] },
              { status: 400 },
            )
          : HttpResponse.json(employeePage);
      }),
    );
    const titles = Array.from({ length: 21 }, (_, n) => `Title ${n + 1}`).join(',');
    renderApp(`/employees?designation=${encodeURIComponent(titles)}`);

    const field = await screen.findByRole('textbox', { name: 'Designation' });
    await waitFor(() => expect(field).toBeInvalid());
    expect(field).toHaveAccessibleDescription('designation accepts at most 20 titles');
    expect(screen.queryByText(/Could not load employees/)).not.toBeInTheDocument();
    expect(screen.getByRole('grid')).toBeInTheDocument();
  });

  it("shows a refused country under the Country field, in the API's words (D76)", async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({ country: ['Unknown country_code: XX'] }, { status: 400 }),
      ),
    );
    renderApp('/employees?country=XX');

    const country = await screen.findByRole('combobox', { name: 'Country' });
    const field = country.closest('.MuiFormControl-root') as HTMLElement;
    expect(await within(field).findByText('Unknown country_code: XX')).toBeInTheDocument();
    expect(country).toHaveAccessibleDescription('Unknown country_code: XX');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText(/Could not load employees/)).not.toBeInTheDocument();
  });

  it('says a refusal the bar has no field for above the grid, never as a lost connection', async () => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({ on: ['Enter a valid date.'] }, { status: 400 }),
      ),
    );
    renderApp('/employees');

    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a valid date.');
    expect(screen.queryByText(/Could not load employees/)).not.toBeInTheDocument();
  });

  it.each([
    ['1 employee', 1, ''],
    ['4 employees', 4, ''],
    ['1 employee matches', 1, '?search=asha'],
    ['4 employees match', 4, '?search=a'],
  ])('says "%s" for %i employees at /employees%s', async (text, count, search) => {
    server.use(
      http.get('/api/v1/employees/', () =>
        HttpResponse.json({
          ...employeePage,
          count,
          results: employeePage.results.slice(0, count),
        }),
      ),
    );
    renderApp(`/employees${search}`);

    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it('says Gross min is above Gross max under the two fields, the grid as the API answers (D76)', async () => {
    recordRequests();
    renderApp('/employees?gross_min=900000&gross_max=100000');

    await screen.findByText('Gross min is above Gross max');
    for (const label of ['Gross min (USD)', 'Gross max (USD)']) {
      const field = screen.getByLabelText(label);
      expect(field).toBeInvalid();
      expect(field).toHaveAccessibleDescription('Gross min is above Gross max');
    }
    expect(screen.getByRole('grid')).toBeInTheDocument();
  });

  it('says nothing about a gross range whose min is at or below its max', async () => {
    recordRequests();
    renderApp('/employees?gross_min=100000&gross_max=100000');

    await rowsShown();
    expect(screen.queryByText('Gross min is above Gross max')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Gross min (USD)')).toBeValid();
  });

  it('tells how to give several titles under the Designation field (D76)', async () => {
    recordRequests();
    renderApp('/employees');

    expect(await screen.findByRole('textbox', { name: 'Designation' })).toHaveAccessibleDescription(
      'Commas between titles, Enter applies',
    );
  });

  it('opens a link to a page past the last on the last page, the URL replaced (D77)', async () => {
    server.use(
      http.get('/api/v1/employees/', ({ request }) => {
        const params = new URL(request.url).searchParams;
        return Number(params.get('page') ?? '1') > 6
          ? HttpResponse.json({ detail: 'Invalid page.' }, { status: 404 })
          : HttpResponse.json(sixtyRows(params));
      }),
    );
    const { router } = renderApp('/employees?country=IN&page=5000');

    await waitFor(() => expect(router.state.location.search).toBe('?country=IN&page=6'));
    expect(router.state.historyAction).toBe('REPLACE');
    expect(await screen.findByText('ACME-51')).toBeInTheDocument();
    expect(screen.queryByText(/Could not load/)).not.toBeInTheDocument();
  });

  it('opens a link past the only page on page 1, the page left out of the URL (D77)', async () => {
    server.use(
      http.get('/api/v1/employees/', ({ request }) => {
        const params = new URL(request.url).searchParams;
        return Number(params.get('page') ?? '1') > 1
          ? HttpResponse.json({ detail: 'Invalid page.' }, { status: 404 })
          : HttpResponse.json(employeePage);
      }),
    );
    const { router } = renderApp('/employees?page=3');

    await waitFor(() => expect(router.state.location.search).toBe(''));
    expect(await screen.findByText('Asha Rao')).toBeInTheDocument();
    expect(screen.queryByText(/Could not load/)).not.toBeInTheDocument();
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
  it('labels every filter and the search', async () => {
    renderApp('/employees');
    await rowsShown();

    expectEveryFieldLabelled();
  });
});
