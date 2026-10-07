import type { JsonBodyType } from 'msw';

import type { ExchangeRates, InsightPayloads, LevelRow } from '../../api/types';

// Insight payloads in the shapes of DESIGN 1.6, with the figures DESIGN section 9 works out by
// hand for the backend fixture, in USD with no filter.

const USD = {
  currency: 'USD',
  rate_month: { label: 'October 2026 rates', effective_from: '2026-10-01' },
};

export const summary: InsightPayloads['summary'] = {
  ...USD,
  headcount: 27,
  total_cost: '2435450.00',
  mean_gross: '80462.96',
  median_gross: '75000.00',
  countries: 4,
  departments: 4,
};

/** With `include_exited`: the fixture's two exited employees, X1 and X2, count too. */
export const summaryWithExited: InsightPayloads['summary'] = {
  ...summary,
  headcount: 29,
  total_cost: '2574450.00',
  mean_gross: '79267.24',
};

export const nobody: InsightPayloads['summary'] = {
  ...summary,
  headcount: 0,
  total_cost: null,
  mean_gross: null,
  median_gross: null,
  countries: 0,
  departments: 0,
};

function country(
  code: string,
  name: string,
  headcount: number,
  total: string | null,
  median: string | null,
  share: string | null,
) {
  return {
    country: { code, name },
    headcount,
    total_cost: total,
    median_gross: median,
    share_pct: share,
  };
}

export const byCountry: InsightPayloads['by-country'] = {
  ...USD,
  rows: [
    country('US', 'United States', 10, '1595000.00', '145000.00', '65.5'),
    country('DE', 'Germany', 4, '450000.00', null, '18.5'),
    country('IN', 'India', 12, '319200.00', '23750.00', '13.1'),
    country('GB', 'United Kingdom', 1, '71250.00', null, '2.9'),
    country('NL', 'Netherlands', 0, null, null, null),
    country('SG', 'Singapore', 0, null, null, null),
  ],
};

function department(
  code: string,
  name: string,
  headcount: number,
  total: string | null,
  mean: string | null,
  median: string | null,
) {
  return {
    department: { code, name },
    headcount,
    total_cost: total,
    mean_gross: mean,
    median_gross: median,
  };
}

export const byDepartment: InsightPayloads['by-department'] = {
  ...USD,
  rows: [
    department('engineering', 'Engineering', 15, '1219200.00', '71500.00', '87500.00'),
    department('sales', 'Sales', 5, '935000.00', '170000.00', '170000.00'),
    department('customer-support', 'Customer Support', 6, '210000.00', '31250.00', '31250.00'),
    department('finance', 'Finance', 1, '71250.00', null, null),
    department('legal', 'Legal', 0, null, null, null),
  ],
};

const EDGES = [
  '10650.00',
  '25379.17',
  '40108.33',
  '54837.50',
  '69566.67',
  '84295.83',
  '99025.00',
  '113754.17',
  '128483.33',
  '143212.50',
  '157941.67',
  '172670.83',
];
const COUNTS = [7, 5, 0, 1, 1, 1, 4, 1, 2, 1, 2, 2];

export const distribution: InsightPayloads['distribution'] = {
  ...USD,
  headcount: 27,
  p1: '10650.00',
  p99: '187400.00',
  bands: EDGES.map((from, index) => ({
    index,
    from,
    to: EDGES[index + 1] ?? '187400.00',
    count: COUNTS[index],
  })),
  markers: { p10: '16500.00', p50: '75000.00', p90: '164000.00' },
};

function level(
  number: number,
  headcount: number,
  figures?: [string, string, string, string, string],
): LevelRow {
  const [min, p25, median, p75, max] = figures ?? [null, null, null, null, null];
  return { level: number, headcount, min, p25, median, p75, max };
}

export const byLevel: InsightPayloads['by-level'] = {
  ...USD,
  rows: [
    level(1, 4),
    level(2, 6, ['12500.00', '36250.00', '68750.00', '108750.00', '130000.00']),
    level(3, 5, ['15000.00', '30000.00', '87500.00', '140000.00', '150000.00']),
    level(4, 5, ['17500.00', '32500.00', '100000.00', '160000.00', '170000.00']),
    level(5, 4),
    level(6, 3),
  ],
};

function gap(
  code: string | null,
  name: string | null,
  women: [number, string | null],
  men: [number, string | null],
  pct: string | null,
) {
  return {
    country: code && name ? { code, name } : null,
    female: { headcount: women[0], median_gross: women[1] },
    male: { headcount: men[0], median_gross: men[1] },
    other_count: 0,
    undisclosed_count: 0,
    gap_pct: pct,
    reason: pct === null ? 'group too small' : null,
  };
}

export const genderGap: InsightPayloads['gender-gap'] = {
  ...USD,
  rows: [
    gap('DE', 'Germany', [2, null], [2, null], null),
    gap('IN', 'India', [6, '25000.00'], [6, '22500.00'], '-11.1'),
    gap('NL', 'Netherlands', [0, null], [0, null], null),
    gap('SG', 'Singapore', [0, null], [0, null], null),
    gap('GB', 'United Kingdom', [1, null], [0, null], null),
    gap('US', 'United States', [4, null], [6, '125000.00'], null),
    gap(null, null, [13, '62500.00'], [14, '100000.00'], '37.5'),
  ],
};

/** Each insight's payload, by the name in its URL. */
export function insightFor(name: string, includeExited: boolean): JsonBodyType | undefined {
  const payloads: Record<string, unknown> = {
    summary: includeExited ? summaryWithExited : summary,
    'by-country': byCountry,
    'by-department': byDepartment,
    distribution,
    'by-level': byLevel,
    'gender-gap': genderGap,
  };
  return payloads[name] as JsonBodyType | undefined;
}

export const exchangeRates: ExchangeRates = {
  on: '2026-10-07',
  rates: [
    { from_currency: 'INR', to_currency: 'USD', rate: '0.01250000', effective_from: '2026-10-01' },
    { from_currency: 'USD', to_currency: 'EUR', rate: '0.80000000', effective_from: '2026-10-01' },
  ],
  month_labels: { USD: 'October 2026 rates', EUR: 'October 2026 rates' },
};
