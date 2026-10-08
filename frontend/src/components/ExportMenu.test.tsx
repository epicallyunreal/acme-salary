import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExportFile } from '../api/exports';
import { setSession } from '../lib/auth';
import { renderApp, renderWithProviders } from '../test/render';
import { server } from '../test/setup';
import { ExportMenu } from './ExportMenu';

/** jsdom has no object URLs and does not follow links, so each save is caught at the click. */
function catchSaves(): string[] {
  vi.stubGlobal(
    'URL',
    Object.assign(class extends URL {}, {
      createObjectURL: vi.fn(() => 'blob:export'),
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

/** Each export request as `path?query` with its query sorted and its bearer token, answered
 * with a file named the way the API names it. */
function recordRequests(): string[] {
  const asked: string[] = [];
  const answer = (request: Request, what: string) => {
    const url = new URL(request.url);
    url.searchParams.sort();
    asked.push(`${url.pathname}?${url.searchParams} ${request.headers.get('authorization')}`);
    const name = `acme-${what}-20261007-0900.${url.searchParams.get('file')}`;
    return new HttpResponse(new Blob(['file']), {
      headers: { 'Content-Disposition': `attachment; filename="${name}"` },
    });
  };
  server.use(
    http.get('/api/v1/exports/employees/', ({ request }) => answer(request, 'employees')),
    http.get('/api/v1/exports/insights/:name/', ({ request, params }) =>
      answer(request, String(params.name)),
    ),
  );
  return asked;
}

describe('ExportMenu', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('offers CSV, Excel and JSON and exports the one chosen', async () => {
    const user = userEvent.setup();
    const onExport = vi.fn<(file: ExportFile) => Promise<void>>(() => Promise.resolve());
    renderWithProviders(
      <ExportMenu label="Export summary" what="the summary" onExport={onExport} />,
    );

    await user.click(screen.getByRole('button', { name: 'Export summary' }));
    // The menu is named by its trigger, so six of them on the dashboard are told apart.
    expect(screen.getByRole('menu', { name: 'Export summary' })).toBeInTheDocument();
    expect(screen.getAllByRole('menuitem').map((item) => item.textContent)).toEqual([
      'CSV',
      'Excel (.xlsx)',
      'JSON',
    ]);
    await user.click(screen.getByRole('menuitem', { name: 'Excel (.xlsx)' }));

    expect(onExport).toHaveBeenCalledWith('xlsx');
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('reads Export and says what it exports in its tooltip', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ExportMenu label="Export summary" what="the summary" onExport={() => Promise.resolve()} />,
    );

    await user.hover(screen.getByRole('button', { name: 'Export summary' }));

    expect(screen.getByRole('button', { name: 'Export summary' })).toHaveTextContent('Export');
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Export summary');
  });

  it('shows the file is on its way and ignores a second click meanwhile', async () => {
    const user = userEvent.setup();
    let finish = () => {};
    const onExport = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
    renderWithProviders(
      <ExportMenu label="Export employees" what="the employees" onExport={onExport} />,
    );
    const trigger = screen.getByRole('button', { name: 'Export employees' });

    await user.click(trigger);
    await user.click(screen.getByRole('menuitem', { name: 'CSV' }));
    await waitFor(() => expect(trigger).toHaveAttribute('aria-busy', 'true'));
    await user.click(trigger);

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    finish();
    await waitFor(() => expect(trigger).not.toHaveAttribute('aria-busy'));
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it('says so when an export fails, and names what failed', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ExportMenu
        label="Export pay by level"
        what="the pay by level"
        onExport={() => Promise.reject(new Error('offline'))}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Export pay by level' }));
    await user.click(screen.getByRole('menuitem', { name: 'JSON' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Could not export the pay by level. Check your connection and try again.',
    );
  });
});

describe('Export menus on the pages', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('exports every page of the directory with its filters, search and sort', async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    const asked = recordRequests();
    renderApp('/employees?country=IN&search=rao&ordering=-gross&page=2&page_size=50');

    await user.click(await screen.findByRole('button', { name: 'Export employees' }));
    await user.click(screen.getByRole('menuitem', { name: 'CSV' }));

    await waitFor(() => expect(saved).toEqual(['acme-employees-20261007-0900.csv']));
    expect(asked).toEqual([
      '/api/v1/exports/employees/?country=IN&file=csv&ordering=-gross&search=rao Bearer access-1',
    ]);
  });

  it("exports a card's table with the dashboard's filters", async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    const asked = recordRequests();
    renderApp('/?country=IN&currency=local&include_exited=true');

    await user.click(await screen.findByRole('button', { name: 'Export pay by level' }));
    await user.click(screen.getByRole('menuitem', { name: 'JSON' }));

    await waitFor(() => expect(saved).toEqual(['acme-by-level-20261007-0900.json']));
    expect(asked).toEqual([
      '/api/v1/exports/insights/by-level/?country=IN&currency=local&file=json&include_exited=true Bearer access-1',
    ]);
  });

  it("exports the summary with the dashboard's filters", async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    const asked = recordRequests();
    renderApp('/?department=engineering');

    await user.click(await screen.findByRole('button', { name: 'Export summary' }));
    await user.click(screen.getByRole('menuitem', { name: 'Excel (.xlsx)' }));

    await waitFor(() => expect(saved).toEqual(['acme-summary-20261007-0900.xlsx']));
    expect(asked).toEqual([
      '/api/v1/exports/insights/summary/?currency=usd&department=engineering&file=xlsx Bearer access-1',
    ]);
  });

  it.each([
    ['Where does payroll go, by country?', 'Export payroll by country', 'by-country'],
    ['Which departments cost most and pay most?', 'Export payroll by department', 'by-department'],
    ['How are salaries distributed?', 'Export salary distribution', 'distribution'],
    ['What does each level pay?', 'Export pay by level', 'by-level'],
    ['Is there a gender pay gap?', 'Export gender pay gap', 'gender-gap'],
    ['How has total cost moved over two years?', 'Export cost trend', 'trend'],
    ['Why did total cost move over the year?', 'Export cost bridge', 'cost-bridge'],
  ])('the card "%s" exports its own table', async (question, label, name) => {
    const user = userEvent.setup();
    const saved = catchSaves();
    renderApp('/');

    const card = await screen.findByRole('region', { name: question });
    await user.click(within(card).getByRole('button', { name: label }));
    await user.click(screen.getByRole('menuitem', { name: 'CSV' }));

    await waitFor(() => expect(saved).toEqual([`acme-${name}-20261007-0900.csv`]));
  });

  it("a card's export sends its control as the URL holds it", async () => {
    const user = userEvent.setup();
    const saved = catchSaves();
    const asked = recordRequests();
    renderApp('/?trend.measure=headcount');

    await user.click(await screen.findByRole('button', { name: 'Export cost trend' }));
    await user.click(screen.getByRole('menuitem', { name: 'CSV' }));

    await waitFor(() => expect(saved).toEqual(['acme-trend-20261007-0900.csv']));
    expect(asked).toEqual([
      '/api/v1/exports/insights/trend/?currency=usd&file=csv&measure=headcount Bearer access-1',
    ]);
  });

  it('a failed download says so on the page it was asked from', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('/api/v1/exports/employees/', () => HttpResponse.json({}, { status: 500 })),
    );
    renderApp('/employees');

    await user.click(await screen.findByRole('button', { name: 'Export employees' }));
    await user.click(screen.getByRole('menuitem', { name: 'JSON' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Could not export the employees. Check your connection and try again.',
    );
  });
});
