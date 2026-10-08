import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { JsonBodyType } from 'msw';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { useInsight } from '../../api/insights';
import { setSession } from '../../lib/auth';
import { costBridgeShown, distribution, summary } from '../../test/fixtures/insights';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/setup';
import { DASHBOARD_DEFAULTS } from '../filters/useDashboardFilters';
import { ByCountryCard } from './ByCountryCard';
import { ByDepartmentCard } from './ByDepartmentCard';
import { ByLevelCard } from './ByLevelCard';
import { ByTenureCard } from './ByTenureCard';
import { CostBridgeCard } from './CostBridgeCard';
import { CostMixCard } from './CostMixCard';
import { DistributionCard } from './DistributionCard';
import { GenderGapCard } from './GenderGapCard';
import { KpiRow } from './KpiRow';
import { TrendCard } from './TrendCard';

function Kpis() {
  const query = useInsight('summary', DASHBOARD_DEFAULTS);
  return <KpiRow query={query} />;
}
function Countries() {
  const query = useInsight('by-country', DASHBOARD_DEFAULTS);
  return <ByCountryCard query={query} />;
}
function Departments() {
  const query = useInsight('by-department', DASHBOARD_DEFAULTS);
  return <ByDepartmentCard query={query} />;
}
function Spread() {
  const query = useInsight('distribution', DASHBOARD_DEFAULTS);
  return <DistributionCard query={query} />;
}
function Levels() {
  const query = useInsight('by-level', DASHBOARD_DEFAULTS);
  return <ByLevelCard query={query} />;
}
function Gap() {
  const query = useInsight('gender-gap', DASHBOARD_DEFAULTS);
  return <GenderGapCard query={query} />;
}
function Mixes() {
  const query = useInsight('cost-mix', DASHBOARD_DEFAULTS, { view: 'cost' });
  return <CostMixCard query={query} />;
}
function Tenures() {
  const query = useInsight('by-tenure', DASHBOARD_DEFAULTS, { level: 'all' });
  return <ByTenureCard query={query} />;
}
function Bridge({ includeExited = false }: { includeExited?: boolean }) {
  const query = useInsight('cost-bridge', DASHBOARD_DEFAULTS);
  return <CostBridgeCard query={query} includeExited={includeExited} />;
}
function Trend({ includeExited = false }: { includeExited?: boolean }) {
  const query = useInsight('trend', DASHBOARD_DEFAULTS, { measure: 'total_cost' });
  return <TrendCard query={query} measure="total_cost" includeExited={includeExited} />;
}

/** One row of a chart's table, read the way a screen reader reads it. */
async function row(caption: string, name: string): Promise<string[]> {
  const table = await screen.findByRole('table', { name: caption });
  const header = within(table).getByRole('rowheader', { name });
  const cells = within(header.closest('tr') as HTMLElement).getAllByRole('cell');
  return cells.map((cell) => (cell.textContent ?? '').replace(/\s+/g, ' '));
}

function answer(name: string, payload: JsonBodyType) {
  server.use(http.get(`/api/v1/insights/${name}/`, () => HttpResponse.json(payload)));
}

const UNDER_FIVE = 'fewer than 5 people';
const UNDER_TWENTY = 'fewer than 20 people';

describe('insight cards', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('the key figures show headcount, total cost, mean and median with their counts', async () => {
    renderWithProviders(<Kpis />);
    const kpis = await screen.findByRole('region', { name: 'Key figures' });

    expect(await within(kpis).findByText('27')).toBeInTheDocument();
    expect(within(kpis).getByText('4 countries')).toBeInTheDocument();
    expect(within(kpis).getByTitle(/^USD\s2,435,450$/)).toHaveTextContent('2.4M');
    expect(within(kpis).getByText('4 departments')).toBeInTheDocument();
    expect(within(kpis).getByText('80,463')).toBeInTheDocument();
    expect(within(kpis).getByText('75,000')).toBeInTheDocument();
  });

  it('the key figures show a population under five by its headcount alone', async () => {
    answer('summary', {
      ...summary,
      headcount: 3,
      total_cost: null,
      mean_gross: null,
      median_gross: null,
    });
    renderWithProviders(<Kpis />);
    const kpis = await screen.findByRole('region', { name: 'Key figures' });

    expect(await within(kpis).findByText('3')).toBeInTheDocument();
    expect(within(kpis).getAllByText('—')).toHaveLength(3);
    expect(within(kpis).getAllByText('Shown for 5 people or more')).toHaveLength(3);
  });

  it('by country lists every country, a small one by its headcount alone', async () => {
    renderWithProviders(<Countries />);

    expect(await row('Payroll by country', 'United States')).toEqual([
      '10',
      'USD 1,595,000',
      'USD 145,000',
      '65.5%',
    ]);
    expect(await row('Payroll by country', 'Germany')).toEqual([
      '4',
      UNDER_FIVE,
      UNDER_FIVE,
      UNDER_FIVE,
    ]);
    expect(await row('Payroll by country', 'Netherlands')).toEqual(['0', '—', '—', '—']);
    expect(
      screen.getByText('Not shown, fewer than 5 people: Germany, United Kingdom.'),
    ).toBeInTheDocument();
  });

  it('by department lists every department and names the small and the empty ones', async () => {
    renderWithProviders(<Departments />);

    expect(await row('Payroll by department', 'Engineering')).toEqual([
      '15',
      'USD 1,219,200',
      'USD 71,500',
      'USD 87,500',
    ]);
    expect(await row('Payroll by department', 'Finance')).toEqual([
      '1',
      UNDER_FIVE,
      UNDER_FIVE,
      UNDER_FIVE,
    ]);
    expect(await row('Payroll by department', 'Legal')).toEqual(['0', '—', '—', '—']);
    expect(screen.getByText('Not shown, fewer than 5 people: Finance.')).toBeInTheDocument();
    expect(screen.getByText('Nobody in Legal.')).toBeInTheDocument();
  });

  it('the distribution gives each band and the three markers', async () => {
    renderWithProviders(<Spread />);

    expect(await row('Salary distribution', 'Band 1')).toEqual(['USD 10,650', 'USD 25,379', '7']);
    expect(await row('Salary distribution', 'Band 3')).toEqual(['USD 40,108', 'USD 54,838', '0']);
    expect(await row('Salary distribution', 'Band 12')).toEqual([
      'USD 172,671',
      'USD 187,400',
      '2',
    ]);
    expect(screen.getByText(/^p10 USD\s16,500$/)).toBeInTheDocument();
    expect(screen.getByText(/^median USD\s75,000$/)).toBeInTheDocument();
    expect(screen.getByText(/^p90 USD\s164,000$/)).toBeInTheDocument();
  });

  it.each([
    [12, 'Shown for 20 people or more; these filters match 12.'],
    [0, 'Nobody matches these filters.'],
  ])('a distribution of %i people says why it has no chart', async (headcount, message) => {
    answer('distribution', {
      ...distribution,
      headcount,
      p1: null,
      p99: null,
      bands: null,
      markers: null,
    });
    renderWithProviders(<Spread />);

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Salary distribution' })).not.toBeInTheDocument();
  });

  it('a distribution of one salary is one sentence', async () => {
    answer('distribution', {
      ...distribution,
      headcount: 20,
      p1: '87500.00',
      p99: '87500.00',
      bands: [{ index: 0, from: '87500.00', to: '87500.00', count: 20 }],
      markers: { p10: '87500.00', p50: '87500.00', p90: '87500.00' },
    });
    renderWithProviders(<Spread />);

    expect(
      await screen.findByText(/^All 20 people in these filters earn USD\s87,500\.$/),
    ).toBeInTheDocument();
  });

  it('by level gives p10 to p90 for twenty people, and names the levels it withholds', async () => {
    renderWithProviders(<Levels />);

    expect(await row('Pay by level', 'Level 1')).toEqual([
      '20',
      'USD 54,750',
      'USD 61,875',
      'USD 73,750',
      'USD 85,625',
      'USD 92,750',
    ]);
    expect(await row('Pay by level', 'Level 2')).toEqual(['19', ...Array(5).fill(UNDER_TWENTY)]);
    expect(
      screen.getByText('Not shown, fewer than 20 people: L2, L3, L4, L5, L6.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Dot: median. Bar: p25 to p75. Whiskers: p10 to p90.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/\b(min|max|range)\b/i)).not.toBeInTheDocument();
  });

  it('the gender gap gives each country and overall, and why a gap is missing', async () => {
    renderWithProviders(<Gap />);

    expect(await row('Gender pay gap', 'India')).toEqual([
      '6',
      'USD 25,000',
      '6',
      'USD 22,500',
      '0',
      '0',
      '-11.1%',
    ]);
    expect(await row('Gender pay gap', 'United States')).toEqual([
      '4',
      UNDER_FIVE,
      '6',
      'USD 125,000',
      '0',
      '0',
      'group too small',
    ]);
    expect(await row('Gender pay gap', 'Overall')).toEqual([
      '13',
      'USD 62,500',
      '14',
      'USD 100,000',
      '0',
      '0',
      '37.5%',
    ]);
  });

  it('the trend names its latest month-end and rates, and its gaps, month by month', async () => {
    renderWithProviders(<Trend />);

    expect(
      await screen.findByText('Month-end totals, latest 30 Sept 2026, at October 2026 rates.'),
    ).toBeInTheDocument();
    expect(await row('Cost trend by month-end', '31 Oct 2024')).toEqual(['4', UNDER_FIVE]);
    expect(await row('Cost trend by month-end', '30 Sept 2026')).toEqual(['27', 'USD 2,435,450']);
    expect(
      screen.getByText(
        'A gap is a month-end with fewer than 5 people, where total cost is not shown.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Include exited doesn't apply/)).not.toBeInTheDocument();
  });

  it('the trend says Include exited does not apply to it while the box is ticked', async () => {
    renderWithProviders(<Trend includeExited />);

    expect(
      await screen.findByText("Counts people employed on each date; Include exited doesn't apply"),
    ).toBeInTheDocument();
  });

  it('the bridge gives each part signed, its dates and rates', async () => {
    answer('cost-bridge', costBridgeShown);
    renderWithProviders(<Bridge />);

    expect(
      await screen.findByText('From 7 Oct 2025 to 7 Oct 2026, at October 2026 rates.'),
    ).toBeInTheDocument();
    expect(await row('Cost bridge for the year', 'Start')).toEqual(['6', 'USD 415,000']);
    expect(await row('Cost bridge for the year', 'Leavers')).toEqual(['0', 'USD 0']);
    expect(await row('Cost bridge for the year', 'Joiners')).toEqual(['5', '+USD 295,000']);
    expect(await row('Cost bridge for the year', 'Pay changes')).toEqual(['6', '+USD 23,000']);
    expect(await row('Cost bridge for the year', 'End')).toEqual(['11', 'USD 733,000']);
    expect(screen.queryByText(/any one could be worked out/)).not.toBeInTheDocument();
  });

  it('a bridge with a short change shows the three by their people, and says why', async () => {
    renderWithProviders(<Bridge includeExited />);

    expect(await row('Cost bridge for the year', 'Leavers')).toEqual(['1', UNDER_FIVE]);
    expect(await row('Cost bridge for the year', 'Joiners')).toEqual([
      '0',
      'withheld with the leavers',
    ]);
    expect(await row('Cost bridge for the year', 'End')).toEqual(['27', 'USD 2,435,450']);
    expect(
      screen.getByText(
        'Leavers, joiners and pay changes are shown when none of them has 1 to 4 people, since any one could be worked out from the others.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Counts people employed on each date; Include exited doesn't apply"),
    ).toBeInTheDocument();
  });

  it('by tenure gives each band and names the short one', async () => {
    renderWithProviders(<Tenures />);

    expect(await row('Median gross by tenure', 'Under 1 year')).toEqual(['3', UNDER_FIVE]);
    expect(await row('Median gross by tenure', '5 to 10 years')).toEqual(['10', 'USD 90,000']);
    expect(await row('Median gross by tenure', '10 years or more')).toEqual(['0', '—']);
    expect(screen.getByText('Not shown, fewer than 5 people: Under 1 year.')).toBeInTheDocument();
  });

  it('the cost mix gives each country its shares and names the short ones', async () => {
    renderWithProviders(<Mixes />);

    expect(await row('Shares of total cost by country', 'United States')).toEqual([
      '10',
      'Base salary 90.9%, Bonus 0.0%, Employer contribution 9.1%',
    ]);
    expect(await row('Shares of total cost by country', 'Germany')).toEqual(['4', UNDER_FIVE]);
    expect(await row('Shares of total cost by country', 'Netherlands')).toEqual(['0', '—']);
    expect(
      screen.getByText('Not shown, fewer than 5 people: Germany, United Kingdom.'),
    ).toBeInTheDocument();
  });

  it('a card that fails to load says so, and its Retry loads it', async () => {
    let failing = true;
    server.use(
      http.get('/api/v1/insights/by-country/', () =>
        failing ? HttpResponse.json({ detail: 'down' }, { status: 500 }) : undefined,
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<Countries />);

    expect(
      await screen.findByText(
        'Could not load the payroll by country. Check your connection and try again.',
      ),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('table', { name: 'Payroll by country' })).toBeInTheDocument();
  });
});
