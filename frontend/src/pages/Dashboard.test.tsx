import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { exchangeRates, insightFor, nobody } from '../test/fixtures/insights';
import { renderApp } from '../test/render';
import { server } from '../test/setup';
import { expectEveryFieldLabelled } from '../test/a11y';
import { PERIOD_DELAY_MS } from '../components/filters/PeriodControl';

const QUESTIONS = [
  'Where does payroll go, by country?',
  'Which departments cost most and pay most?',
  'How are salaries distributed?',
  'What does each level pay?',
  'Is there a gender pay gap? (on annual pay)',
  'How has total cost moved over the period?',
  'Why did total cost move over the period?',
  'Does pay rise with tenure?',
  'What is pay made of?',
];
const SECTIONS = ['What we spend', 'How pay is structured', 'Is pay fair'];
const UNREADABLE_PERIOD =
  "This link's period could not be read, so the dashboard shows the last 12 months.";
const INSIGHTS = [
  'by-country',
  'by-department',
  'by-level',
  'by-tenure',
  'cost-bridge',
  'cost-mix',
  'distribution',
  'gender-gap',
  'summary',
  'trend',
];

/** Answers every insight from the fixtures over the period it asks for, as the API would, and
 * records the query string of each request. */
function recordRequests() {
  const seen: Record<string, URLSearchParams[]> = {};
  server.use(
    http.get('/api/v1/insights/:name/', ({ request, params }) => {
      const name = String(params.name);
      const query = new URL(request.url).searchParams;
      (seen[name] ??= []).push(query);
      const payload = insightFor(name, query.get('include_exited') === 'true', query.get('view'));
      return HttpResponse.json({
        ...(payload as Record<string, unknown>),
        from: query.get('from'),
        to: query.get('to'),
      });
    }),
  );
  return seen;
}

/** The period a request asked for. */
function dates(query: URLSearchParams | undefined): (string | null)[] {
  return [query?.get('from') ?? null, query?.get('to') ?? null];
}

/** Answers every insight in the currency the request asks for, as the API would. */
function answerInTheAskedCurrency() {
  const local: Record<string, string> = { IN: 'INR', DE: 'EUR' };
  server.use(
    http.get('/api/v1/insights/:name/', ({ request, params }) => {
      const query = new URL(request.url).searchParams;
      const asked = query.get('currency') ?? 'usd';
      const code = asked === 'local' ? local[query.get('country') ?? ''] : asked.toUpperCase();
      const payload = insightFor(String(params.name), false) as Record<string, unknown>;
      const rateMonth =
        asked === 'local'
          ? { label: `local currency (${code})`, effective_from: null }
          : payload.rate_month;
      return HttpResponse.json({ ...payload, currency: code, rate_month: rateMonth });
    }),
  );
}

async function keyFigures() {
  return screen.findByRole('region', { name: 'Key figures' });
}

describe('Dashboard', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    // Today is 7 October 2026 in UTC, the day the fixtures stand on.
    vi.setSystemTime(new Date('2026-10-07T09:00:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('answers every question for the whole company, under three headings', async () => {
    renderApp('/');

    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(await within(await keyFigures()).findByText('27')).toBeInTheDocument();
    expect(screen.getByText('October 2026 rates for the whole period')).toBeInTheDocument();
    for (const section of SECTIONS) {
      expect(await screen.findByRole('heading', { level: 2, name: section })).toBeInTheDocument();
    }
    for (const question of QUESTIONS) {
      expect(await screen.findByRole('heading', { level: 3, name: question })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
  });

  it('keeps a quiet link beside the filters that opens the answer on hidden figures', async () => {
    renderApp('/');
    const user = userEvent.setup();
    const filters = await screen.findByRole('region', { name: 'Filters' });
    const link = within(filters).getByRole('link', { name: 'Why are some figures hidden?' });
    expect(link).toHaveAttribute('href', '/help#hidden-figures');

    await user.click(link);

    expect(await screen.findByRole('heading', { level: 1, name: 'Help' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Why does a figure say/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('a filter change refetches every card with the new filter', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    renderApp('/');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(Object.keys(seen).sort()).toEqual(INSIGHTS);
      for (const name of INSIGHTS) {
        expect(seen[name].map((query) => query.get('country'))).toContain('IN');
      }
    });
  });

  it("the include-exited box adds the filter's exited employees to the headcount", async () => {
    const user = userEvent.setup();
    renderApp('/');
    const kpis = await keyFigures();
    expect(await within(kpis).findByText('27')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'Include exited' }));

    // The fixture's two exited employees, X1 and X2, now count.
    expect(await within(kpis).findByText('29')).toBeInTheDocument();
    expect(within(kpis).queryByText('27')).not.toBeInTheDocument();
  });

  it('offers the local currency only while one country is selected', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Currency'));
    expect(await screen.findByRole('option', { name: 'EUR' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Local' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');
    await user.click(screen.getByLabelText('Currency'));

    expect(await screen.findByRole('option', { name: 'Local' })).toBeInTheDocument();
  });

  it('reads its filters from the URL and sends them with every card', async () => {
    const seen = recordRequests();
    renderApp('/?country=IN&currency=local&include_exited=true');

    expect(await within(await keyFigures()).findByText('29')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Include exited' })).toBeChecked();
    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
    for (const name of INSIGHTS) {
      const query = seen[name][0];
      expect([query.get('country'), query.get('currency'), query.get('include_exited')]).toEqual([
        'IN',
        'local',
        'true',
      ]);
    }
  });

  it('keeps local through a switch from India to Germany, and drops it for two countries', async () => {
    answerInTheAskedCurrency();
    const user = userEvent.setup();
    renderApp('/?country=IN&currency=local');
    const kpis = await keyFigures();
    expect(await screen.findByText('Local currency (INR)')).toBeInTheDocument();
    expect(within(kpis).getAllByText('INR')).toHaveLength(4);

    // India to Germany in one visit to the menu: still one country, so local stays.
    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.click(screen.getByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('Local currency (EUR)')).toBeInTheDocument();
    expect(within(kpis).getAllByText('EUR')).toHaveLength(4);

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('October 2026 rates for the whole period')).toBeInTheDocument();
    expect(within(kpis).getAllByText('USD')).toHaveLength(4);
  });

  it('drops local when no country is left', async () => {
    answerInTheAskedCurrency();
    const user = userEvent.setup();
    renderApp('/?country=DE&currency=local');
    expect(await screen.findByText('Local currency (EUR)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('October 2026 rates for the whole period')).toBeInTheDocument();
    expect(within(await keyFigures()).getAllByText('USD')).toHaveLength(4);
  });

  it("the trend's control picks its line, lives in the URL and refetches that card alone", async () => {
    const user = userEvent.setup();
    const seen = recordRequests();
    const { router } = renderApp('/');
    const control = await screen.findByRole('group', { name: 'Trend measure' });
    await waitFor(() => expect(seen.trend).toHaveLength(1));

    await user.click(within(control).getByRole('button', { name: 'Headcount' }));

    await waitFor(() => expect(seen.trend).toHaveLength(2));
    expect(seen.trend[1].get('measure')).toBe('headcount');
    expect(router.state.location.search).toBe('?trend.measure=headcount');
    expect(within(control).getByRole('button', { name: 'Headcount' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    for (const name of INSIGHTS.filter((insight) => insight !== 'trend')) {
      expect(seen[name]).toHaveLength(1);
    }
  });

  it("the tenure card's Level picks the level, in the URL, refetching that card alone", async () => {
    const user = userEvent.setup();
    const seen = recordRequests();
    const { router } = renderApp('/');
    const card = await screen.findByRole('region', { name: 'Does pay rise with tenure?' });
    await waitFor(() => expect(seen['by-tenure']).toHaveLength(1));

    await user.click(within(card).getByRole('combobox', { name: 'Level' }));
    await user.click(await screen.findByRole('option', { name: 'L3' }));

    await waitFor(() => expect(seen['by-tenure']).toHaveLength(2));
    expect(seen['by-tenure'][1].get('level')).toBe('3');
    expect(router.state.location.search).toBe('?tenure.level=3');
    for (const name of INSIGHTS.filter((insight) => insight !== 'by-tenure')) {
      expect(seen[name]).toHaveLength(1);
    }
  });

  it("the cost mix's control switches it to take-home pay, in the URL", async () => {
    const user = userEvent.setup();
    const seen = recordRequests();
    const { router } = renderApp('/');
    const control = await screen.findByRole('group', { name: 'Cost mix view' });
    await waitFor(() => expect(seen['cost-mix']).toHaveLength(1));

    await user.click(within(control).getByRole('button', { name: 'Take-home' }));

    await waitFor(() => expect(seen['cost-mix']).toHaveLength(2));
    expect(seen['cost-mix'][1].get('view')).toBe('take_home');
    expect(router.state.location.search).toBe('?mix.view=take_home');
    for (const name of INSIGHTS.filter((insight) => insight !== 'cost-mix')) {
      expect(seen[name]).toHaveLength(1);
    }
  });

  it("the gender card's control switches its view, in the URL", async () => {
    const user = userEvent.setup();
    const seen = recordRequests();
    const { router } = renderApp('/');
    const control = await screen.findByRole('group', { name: 'Gender gap view' });
    await waitFor(() => expect(seen['gender-gap']).toHaveLength(1));

    await user.click(within(control).getByRole('button', { name: 'Quartiles' }));

    await waitFor(() => expect(seen['gender-gap']).toHaveLength(2));
    expect(seen['gender-gap'][1].get('view')).toBe('quartiles');
    expect(router.state.location.search).toBe('?gap.view=quartiles');
    for (const name of INSIGHTS.filter((insight) => insight !== 'gender-gap')) {
      expect(seen[name]).toHaveLength(1);
    }
    expect(
      await screen.findByRole('table', { name: 'Pay quartiles by gender' }),
    ).toBeInTheDocument();
  });

  it("Clear filters resets all four cards' controls with the bar's filters", async () => {
    const user = userEvent.setup();
    const { router } = renderApp(
      '/?country=IN&trend.measure=headcount&tenure.level=3&mix.view=take_home&gap.view=bonus',
    );

    await user.click(await screen.findByRole('button', { name: 'Clear filters' }));

    expect(router.state.location.search).toBe('');
    const pressed = async (group: string, name: string) =>
      within(await screen.findByRole('group', { name: group })).getByRole('button', { name });
    expect(await pressed('Trend measure', 'Total cost')).toHaveAttribute('aria-pressed', 'true');
    expect(await pressed('Cost mix view', 'Cost')).toHaveAttribute('aria-pressed', 'true');
    expect(await pressed('Gender gap view', 'Pay gap')).toHaveAttribute('aria-pressed', 'true');
    const tenure = await screen.findByRole('region', { name: 'Does pay rise with tenure?' });
    expect(within(tenure).getByRole('combobox', { name: 'Level' })).toHaveTextContent('All');
  });

  it("a filter change keeps the cards' controls, in the URL and in every request", async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    const { router } = renderApp('/?trend.measure=headcount&gap.view=bonus');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(seen.trend.at(-1)?.get('country')).toBe('IN'));
    expect(seen.trend.at(-1)?.get('measure')).toBe('headcount');
    await waitFor(() => expect(seen['gender-gap'].at(-1)?.get('country')).toBe('IN'));
    expect(seen['gender-gap'].at(-1)?.get('view')).toBe('bonus');
    const search = new URLSearchParams(router.state.location.search);
    expect([search.get('trend.measure'), search.get('gap.view')]).toEqual(['headcount', 'bonus']);
  });

  it('reads the last 12 months by default and sends their dates with every card', async () => {
    const seen = recordRequests();
    const { router } = renderApp('/');

    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
    for (const name of INSIGHTS) {
      expect(dates(seen[name][0])).toEqual(['2025-10-08', '2026-10-07']);
      expect(seen[name][0].has('period')).toBe(false);
    }
    expect(screen.getByLabelText('Period')).toHaveTextContent('Last 12 months');
    expect(router.state.location.search).toBe('');
  });

  it('a preset sends its dates with every card, and the URL keeps its name', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    const { router } = renderApp('/');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Period'));
    await user.click(await screen.findByRole('option', { name: 'Last 3 months' }));

    expect(router.state.location.search).toBe('?period=last_3_months');
    await waitFor(() => {
      for (const name of INSIGHTS) {
        expect(seen[name].map(dates)).toContainEqual(['2026-07-08', '2026-10-07']);
      }
    });
  });

  it.each([
    ['last_6_months', 'Last 6 months', '2026-04-08', '2026-10-07'],
    ['fy_to_date', 'Current FY to date', '2026-04-01', '2026-10-07'],
    ['last_fy', 'Last FY', '2025-04-01', '2026-03-31'],
  ])('a link to %s counts back from the day it is opened', async (period, label, from, to) => {
    const seen = recordRequests();
    renderApp(`/?period=${period}`);

    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
    for (const name of INSIGHTS) expect(dates(seen[name][0])).toEqual([from, to]);
    expect(screen.getByLabelText('Period')).toHaveTextContent(label);
  });

  it('Custom starts from the dates on screen, fetching nothing new, and keeps them in the URL', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    const { router } = renderApp('/?period=last_6_months');
    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));

    await user.click(screen.getByLabelText('Period'));
    await user.click(await screen.findByRole('option', { name: 'Custom' }));

    expect(router.state.location.search).toBe('?period=custom&from=2026-04-08&to=2026-10-07');
    expect(await screen.findByLabelText('From')).toHaveValue('2026-04-08');
    expect(screen.getByLabelText('To')).toHaveValue('2026-10-07');
    for (const name of INSIGHTS) expect(seen[name]).toHaveLength(1);
  });

  it('a custom range the API would refuse says why and keeps the last valid period', async () => {
    const seen = recordRequests();
    const { router } = renderApp('/?period=custom&from=2026-01-01&to=2026-03-31');
    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
    for (const name of INSIGHTS) expect(dates(seen[name][0])).toEqual(['2026-01-01', '2026-03-31']);

    const from = screen.getByLabelText('From');
    // The calendar offers nothing before the reporting cut-off (D70).
    expect(from).toHaveAttribute('min', '2020-04-01');
    fireEvent.change(from, { target: { value: '2026-04-15' } });
    fireEvent.keyDown(from, { key: 'Enter' });

    expect(await screen.findByText('From must be on or before To.')).toBeInTheDocument();
    expect(from).toHaveValue('2026-04-15');
    expect(router.state.location.search).toBe('?period=custom&from=2026-01-01&to=2026-03-31');

    const to = screen.getByLabelText('To');
    fireEvent.change(to, { target: { value: '2026-06-30' } });
    fireEvent.keyDown(to, { key: 'Enter' });

    expect(router.state.location.search).toBe('?period=custom&from=2026-04-15&to=2026-06-30');
    expect(screen.queryByText('From must be on or before To.')).not.toBeInTheDocument();
    await waitFor(() => {
      for (const name of INSIGHTS) {
        expect(seen[name].map(dates)).toContainEqual(['2026-04-15', '2026-06-30']);
      }
    });
    for (const name of INSIGHTS) {
      expect(seen[name].map(dates)).not.toContainEqual(['2026-04-15', '2026-03-31']);
    }
  });

  it('a custom date applies on leaving its field, or on its own after a pause', async () => {
    const seen = recordRequests();
    const { router } = renderApp('/?period=custom&from=2026-01-01&to=2026-03-31');
    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));

    const from = screen.getByLabelText('From');
    fireEvent.change(from, { target: { value: '2026-02-01' } });
    fireEvent.blur(from);

    expect(router.state.location.search).toBe('?period=custom&from=2026-02-01&to=2026-03-31');

    // As a date picked from the calendar does, with no Enter and no click elsewhere (D66). The
    // pause is a fake timer that only advancing fires, so the check before it cannot race it.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-04-30' } });
    expect(router.state.location.search).toBe('?period=custom&from=2026-02-01&to=2026-03-31');
    act(() => vi.advanceTimersByTime(PERIOD_DELAY_MS));
    vi.useRealTimers();

    await waitFor(() =>
      expect(router.state.location.search).toBe('?period=custom&from=2026-02-01&to=2026-04-30'),
    );
  });

  it.each([
    ['an unknown preset', '/?country=IN&period=last_99_years'],
    ['an impossible date', '/?country=IN&period=custom&from=2026-02-31&to=2026-03-31'],
    ['a date before the cut-off', '/?country=IN&period=custom&from=2020-03-31&to=2026-01-01'],
  ])(
    'a link whose period cannot be read, with %s, opens on the last 12 months and says so (D76)',
    async (_, url) => {
      const seen = recordRequests();
      const { router } = renderApp(url);

      expect(await screen.findByText(UNREADABLE_PERIOD)).toBeInTheDocument();
      await waitFor(() => expect(router.state.location.search).toBe('?country=IN'));
      expect(router.state.historyAction).toBe('REPLACE');
      // Once the URL reads well, the replacement's state keeps the line.
      expect(screen.getByText(UNREADABLE_PERIOD)).toBeInTheDocument();
      await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
      for (const name of INSIGHTS)
        expect(dates(seen[name].at(-1))).toEqual(['2025-10-08', '2026-10-07']);
      expect(screen.getByLabelText('Period')).toHaveTextContent('Last 12 months');
    },
  );

  it('drops the line about an unreadable period at the next change', async () => {
    recordRequests();
    const user = userEvent.setup();
    renderApp('/?period=last_99_years');
    const line = await screen.findByText(UNREADABLE_PERIOD);

    await user.click(screen.getByRole('checkbox', { name: 'Include exited' }));

    await waitFor(() => expect(line).not.toBeInTheDocument());
  });

  it('says nothing about a period it can read', async () => {
    recordRequests();
    renderApp('/?period=last_fy');

    await keyFigures();
    expect(screen.queryByText(UNREADABLE_PERIOD)).not.toBeInTheDocument();
  });

  it('Clear filters takes the period back to the last 12 months with the rest', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    const { router } = renderApp('/?country=IN&period=custom&from=2026-01-01&to=2026-03-31');

    await user.click(await screen.findByRole('button', { name: 'Clear filters' }));

    expect(router.state.location.search).toBe('');
    expect(screen.getByLabelText('Period')).toHaveTextContent('Last 12 months');
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument();
    await waitFor(() => expect(dates(seen.summary.at(-1))).toEqual(['2025-10-08', '2026-10-07']));
  });

  it('every card that shows a state names its day, and trend and the bridge their period', async () => {
    recordRequests();
    renderApp('/?period=last_fy');

    await waitFor(() => expect(screen.getAllByText('On 31 Mar 2026')).toHaveLength(7));
    expect(
      screen.getAllByText('From 1 Apr 2025 to 31 Mar 2026, at October 2026 rates.'),
    ).toHaveLength(2);
    const kpis = await keyFigures();
    expect(within(kpis).getByText('Headcount on 31 Mar 2026')).toBeInTheDocument();
    expect(within(kpis).getByText('1 Apr 2025 to 31 Mar 2026')).toBeInTheDocument();
  });

  it("the rates behind the label are the ones in force on the period's last day", async () => {
    recordRequests();
    const asked: (string | null)[] = [];
    server.use(
      http.get('/api/v1/meta/exchange-rates/', ({ request }) => {
        asked.push(new URL(request.url).searchParams.get('on'));
        return HttpResponse.json(exchangeRates);
      }),
    );
    renderApp('/?period=last_fy');

    await waitFor(() => expect(asked).toEqual(['2026-03-31']));
  });

  it('a period alone still offers Clear filters', async () => {
    renderApp('/?period=last_fy');

    expect(await screen.findByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('a card control alone still offers Clear filters', async () => {
    renderApp('/?trend.measure=headcount');

    expect(await screen.findByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('says what to do when no one matches the filters', async () => {
    server.use(
      http.get('/api/v1/insights/:name/', ({ params }) =>
        HttpResponse.json(
          params.name === 'summary' ? nobody : insightFor(String(params.name), false),
        ),
      ),
    );
    renderApp('/?country=NL');

    expect(
      await screen.findByText('No one matches these filters today. Clear a filter.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: QUESTIONS[0] })).not.toBeInTheDocument();
    // The filter bar's own button clears them.
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('says there is nobody yet, with the ways to add people, when no filter is set (D78)', async () => {
    server.use(
      http.get('/api/v1/insights/:name/', ({ params }) =>
        HttpResponse.json(
          params.name === 'summary' ? nobody : insightFor(String(params.name), false),
        ),
      ),
    );
    renderApp('/');

    const message = await screen.findByText(/^No employees yet\./);
    expect(message).toHaveTextContent(
      'No employees yet. Import a spreadsheet on the Imports page, or use the sample files on Demo data.',
    );
    expect(within(message).getByRole('link', { name: 'Imports page' })).toHaveAttribute(
      'href',
      '/imports',
    );
    expect(within(message).getByRole('link', { name: 'Demo data' })).toHaveAttribute(
      'href',
      '/demo',
    );
    expect(screen.queryByText(/No one matches these filters/)).not.toBeInTheDocument();
  });

  it('says on which day no one matches when the period ends before today', async () => {
    server.use(
      http.get('/api/v1/insights/:name/', ({ params }) =>
        HttpResponse.json(
          params.name === 'summary'
            ? { ...nobody, from: '2025-04-01', to: '2026-03-31' }
            : insightFor(String(params.name), false),
        ),
      ),
    );
    renderApp('/?country=NL&period=last_fy');

    expect(
      await screen.findByText('No one matches these filters on 31 Mar 2026. Clear a filter.'),
    ).toBeInTheDocument();
  });
  it("shows a filter the API refuses in the API's words, once, under the bar, with Clear filters", async () => {
    const refused: string[] = [];
    server.use(
      http.get('/api/v1/insights/:name/', ({ request, params }) => {
        if (new URL(request.url).searchParams.get('country') !== 'XX')
          return HttpResponse.json(insightFor(String(params.name), false));
        refused.push(String(params.name));
        return HttpResponse.json({ country: ['Unknown country_code: XX'] }, { status: 400 });
      }),
    );
    const { router } = renderApp('/?country=XX');
    const user = userEvent.setup();

    const alert = await screen.findByRole('alert');
    expect(within(alert).getAllByText('Unknown country_code: XX')).toHaveLength(1);
    const bar = screen.getByRole('region', { name: 'Filters' });
    expect(bar.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await waitFor(() => expect([...refused].sort()).toEqual(INSIGHTS));
    // In place of the cards, and never the connection message.
    expect(screen.queryByText(/Could not load/)).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Key figures' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: QUESTIONS[0] })).not.toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: 'Clear filters' }));

    expect(await screen.findByRole('heading', { name: QUESTIONS[0] })).toBeInTheDocument();
    expect(router.state.location.search).toBe('');
  });

  it.each([
    ['the server fails', () => HttpResponse.json({}, { status: 500 })],
    ['no answer comes', () => HttpResponse.error()],
  ])('every card says so when %s, each with its own Retry', async (_, answer) => {
    server.use(http.get('/api/v1/insights/:name/', answer));
    renderApp('/');

    // One per insight the dashboard draws, each with the state table's sentence.
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Retry' })).toHaveLength(10));
    const messages = screen.getAllByText(/Could not load/).map((node) => node.textContent);
    expect(messages).toHaveLength(10);
    for (const message of messages) {
      expect(message).toMatch(/^Could not load .+\. Check your connection and try again\.$/);
    }
  });

  it('labels every filter', async () => {
    renderApp('/');
    await screen.findByLabelText('Period');

    expectEveryFieldLabelled();
  });
});
