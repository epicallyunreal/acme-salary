import { screen, within } from '@testing-library/react';
import type { JsonBodyType } from 'msw';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { useInsight } from '../../api/insights';
import { setSession } from '../../lib/auth';
import { distribution, summary } from '../../test/fixtures/insights';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/setup';
import { DASHBOARD_DEFAULTS } from '../filters/useDashboardFilters';
import { ByCountryCard } from './ByCountryCard';
import { ByDepartmentCard } from './ByDepartmentCard';
import { ByLevelCard } from './ByLevelCard';
import { DistributionCard } from './DistributionCard';
import { GenderGapCard } from './GenderGapCard';
import { KpiRow } from './KpiRow';

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

const WITHHELD = 'fewer than 5 people';

describe('insight cards', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('the key figures show headcount, total cost, mean and median with their counts', async () => {
    renderWithProviders(<Kpis />);

    expect(await screen.findByText('27')).toBeInTheDocument();
    expect(screen.getByText('4 countries')).toBeInTheDocument();
    expect(screen.getByText('2.4M').closest('p')).toHaveAttribute(
      'title',
      expect.stringMatching(/^USD\s2,435,450$/),
    );
    expect(screen.getByText('4 departments')).toBeInTheDocument();
    expect(screen.getByText('80,463')).toBeInTheDocument();
    expect(screen.getByText('75,000')).toBeInTheDocument();
  });

  it('the key figures withhold mean and median for a group under five', async () => {
    answer('summary', { ...summary, headcount: 3, mean_gross: null, median_gross: null });
    renderWithProviders(<Kpis />);

    expect(await screen.findByText('3')).toBeInTheDocument();
    expect(screen.getAllByText('Shown for 5 people or more')).toHaveLength(2);
  });

  it('by country lists every country, withholding the median of a small one', async () => {
    renderWithProviders(<Countries />);

    expect(await row('Payroll by country', 'United States')).toEqual([
      '10',
      'USD 1,595,000',
      'USD 145,000',
      '65.5%',
    ]);
    expect(await row('Payroll by country', 'Germany')).toEqual([
      '4',
      'USD 450,000',
      WITHHELD,
      '18.5%',
    ]);
    expect(await row('Payroll by country', 'Netherlands')).toEqual(['0', '—', '—', '—']);
  });

  it('by department lists every department and names the empty ones', async () => {
    renderWithProviders(<Departments />);

    expect(await row('Payroll by department', 'Engineering')).toEqual([
      '15',
      'USD 1,219,200',
      'USD 71,500',
      'USD 87,500',
    ]);
    expect(await row('Payroll by department', 'Finance')).toEqual([
      '1',
      'USD 71,250',
      WITHHELD,
      WITHHELD,
    ]);
    expect(await row('Payroll by department', 'Legal')).toEqual(['0', '—', '—', '—']);
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

  it('the distribution of under five people says so', async () => {
    answer('distribution', {
      ...distribution,
      headcount: 1,
      p1: null,
      p99: null,
      bands: null,
      markers: null,
    });
    renderWithProviders(<Spread />);

    expect(
      await screen.findByText('Shown for 5 people or more; these filters match 1.'),
    ).toBeInTheDocument();
  });

  it('a distribution of one salary is one sentence', async () => {
    answer('distribution', {
      ...distribution,
      headcount: 5,
      p1: '87500.00',
      p99: '87500.00',
      bands: [{ index: 0, from: '87500.00', to: '87500.00', count: 5 }],
      markers: { p10: '87500.00', p50: '87500.00', p90: '87500.00' },
    });
    renderWithProviders(<Spread />);

    expect(
      await screen.findByText(/^All 5 people in these filters earn USD\s87,500\.$/),
    ).toBeInTheDocument();
  });

  it('by level gives the five figures, and names the levels it withholds', async () => {
    renderWithProviders(<Levels />);

    expect(await row('Pay by level', 'Level 3')).toEqual([
      '5',
      'USD 15,000',
      'USD 30,000',
      'USD 87,500',
      'USD 140,000',
      'USD 150,000',
    ]);
    expect(await row('Pay by level', 'Level 1')).toEqual(['4', ...Array(5).fill(WITHHELD)]);
    expect(screen.getByText('Not shown, fewer than 5 people: L1, L5, L6.')).toBeInTheDocument();
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
      WITHHELD,
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
});
