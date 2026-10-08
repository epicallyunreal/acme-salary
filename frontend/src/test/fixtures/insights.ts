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
    country('IN', 'India', 12, '319200.00', '23750.00', '13.1'),
    // Under five, a country shows its headcount alone (D59), then follows in name order.
    country('DE', 'Germany', 4, null, null, null),
    country('NL', 'Netherlands', 0, null, null, null),
    country('SG', 'Singapore', 0, null, null, null),
    country('GB', 'United Kingdom', 1, null, null, null),
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
    department('finance', 'Finance', 1, null, null, null),
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
  const [p10, p25, median, p75, p90] = figures ?? [null, null, null, null, null];
  return { level: number, headcount, p10, p25, median, p75, p90 };
}

/** Twenty people at level 1, the least D59 shows figures for; every other level is fewer. */
export const byLevel: InsightPayloads['by-level'] = {
  ...USD,
  rows: [
    level(1, 20, ['54750.00', '61875.00', '73750.00', '85625.00', '92750.00']),
    level(2, 19),
    level(3, 5),
    level(4, 5),
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
  // The card's words for who is short (D62).
  const short = [women[0] < 5 ? 'fewer than 5 women' : '', men[0] < 5 ? 'fewer than 5 men' : '']
    .filter(Boolean)
    .join(' and ');
  return {
    country: code && name ? { code, name } : null,
    female: { headcount: women[0], median_gross: women[1] },
    male: { headcount: men[0], median_gross: men[1] },
    other_count: 0,
    undisclosed_count: 0,
    gap_pct: pct,
    // A group with nobody in it gives no reason, as every other table words it (D62).
    reason: pct === null && women[0] + men[0] > 0 ? short : null,
  };
}

export const genderGap: InsightPayloads['gender-gap'] = {
  ...USD,
  view: 'pay_gap',
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

/** The Bonus view: India's women and men compared, mean and median gaps apart, and the US with
 * four women. No mean amount is published (D62). */
export const bonusGap: InsightPayloads['gender-gap'] = {
  ...USD,
  view: 'bonus',
  rows: [
    {
      country: { code: 'IN', name: 'India' },
      female: { headcount: 6, receiving: 5, receiving_pct: '83.3', median_bonus: '3000.00' },
      male: { headcount: 6, receiving: 6, receiving_pct: '100.0', median_bonus: '4500.00' },
      other_count: 1,
      undisclosed_count: 0,
      mean_gap_pct: '40.0',
      median_gap_pct: '33.3',
      reason: null,
    },
    {
      country: { code: 'US', name: 'United States' },
      female: { headcount: 4, receiving: null, receiving_pct: null, median_bonus: null },
      male: { headcount: 6, receiving: null, receiving_pct: null, median_bonus: null },
      other_count: 0,
      undisclosed_count: 0,
      mean_gap_pct: null,
      median_gap_pct: null,
      reason: 'fewer than 5 women',
    },
  ],
};

function quartile(number: number, women: number, men: number) {
  return {
    quartile: number,
    headcount: women + men,
    female: women,
    male: men,
    female_pct: (women * 20).toFixed(1),
    male_pct: (men * 20).toFixed(1),
  };
}

/** The Quartiles view of ten women and ten men, the other and the undisclosed employee counted
 * beside and never ranked (D62). */
export const quartileGap: InsightPayloads['gender-gap'] = {
  ...USD,
  view: 'quartiles',
  headcount: 20,
  other_count: 1,
  undisclosed_count: 1,
  reason: null,
  quartiles: [quartile(1, 2, 3), quartile(2, 3, 2), quartile(3, 3, 2), quartile(4, 2, 3)],
};

/** The Quartiles view withheld: India's twelve women and men are under twenty. */
export const quartileGapWithheld: InsightPayloads['gender-gap'] = {
  ...USD,
  view: 'quartiles',
  headcount: 12,
  other_count: 0,
  undisclosed_count: 0,
  reason: 'fewer than 20 people',
  quartiles: null,
};

function levelGap(
  level: number,
  women: [number, string | null],
  men: [number, string | null],
  gaps: [string, string] | null,
  flagged: boolean,
  reason: string | null = null,
) {
  return {
    country: { code: 'NL', name: 'Netherlands' },
    level,
    female: { headcount: women[0], median_gross: women[1] },
    male: { headcount: men[0], median_gross: men[1] },
    mean_gap_pct: gaps ? gaps[0] : null,
    median_gap_pct: gaps ? gaps[1] : null,
    flagged,
    reason,
  };
}

/** The By level view of the Netherlands: level 1 flagged with its mean and median gaps apart,
 * level 2 not flagged, level 3 short of women, and one other employee counted by country. */
export const levelGapView: InsightPayloads['gender-gap'] = {
  ...USD,
  view: 'by_level',
  rows: [
    levelGap(1, [5, '44000.00'], [5, '48000.00'], ['8.0', '8.3'], true),
    levelGap(2, [5, '50000.00'], [5, '52000.00'], ['3.8', '3.8'], false),
    levelGap(3, [4, null], [6, null], null, false, 'fewer than 5 women'),
  ],
  others: [{ country: { code: 'NL', name: 'Netherlands' }, other_count: 1, undisclosed_count: 0 }],
};

const MONTH_ENDS = [
  '2024-10-31',
  '2024-11-30',
  '2024-12-31',
  '2025-01-31',
  '2025-02-28',
  '2025-03-31',
  '2025-04-30',
  '2025-05-31',
  '2025-06-30',
  '2025-07-31',
  '2025-08-31',
  '2025-09-30',
  '2025-10-31',
  '2025-11-30',
  '2025-12-31',
  '2026-01-31',
  '2026-02-28',
  '2026-03-31',
  '2026-04-30',
  '2026-05-31',
  '2026-06-30',
  '2026-07-31',
  '2026-08-31',
  '2026-09-30',
];

/** Two years of month-ends: four people at the first two, so their totals are withheld (D59),
 * then 26 people at 2,300,000.00, then the 27 of the summary from April 2026. */
export const trend: InsightPayloads['trend'] = {
  ...USD,
  measure: 'total_cost',
  latest: '2026-09-30',
  points: MONTH_ENDS.map((month_end, index) => {
    if (index < 2) return { month_end, headcount: 4, total_cost: null };
    if (index < 18) return { month_end, headcount: 26, total_cost: '2300000.00' };
    return { month_end, headcount: 27, total_cost: '2435450.00' };
  }),
};

/** DESIGN 9's year: X1 the one leaver, so the pay changes go with him, and the joiners, who
 * are nobody, show 0.00 (D62). */
export const costBridge: InsightPayloads['cost-bridge'] = {
  ...USD,
  start_date: '2025-10-07',
  end_date: '2026-10-07',
  parts: [
    { part: 'start', people: 28, amount: '2567450.00', reason: null },
    { part: 'leavers', people: 1, amount: null, reason: 'fewer than 5 people' },
    { part: 'joiners', people: 0, amount: '0.00', reason: null },
    { part: 'pay_changes', people: 27, amount: null, reason: 'withheld with the leavers' },
    { part: 'end', people: 27, amount: '2435450.00', reason: null },
  ],
};

/** A year where every part shows: the history fixture of the backend tests. */
export const costBridgeShown: InsightPayloads['cost-bridge'] = {
  ...USD,
  start_date: '2025-10-07',
  end_date: '2026-10-07',
  parts: [
    { part: 'start', people: 6, amount: '415000.00', reason: null },
    { part: 'leavers', people: 0, amount: '0.00', reason: null },
    { part: 'joiners', people: 5, amount: '295000.00', reason: null },
    { part: 'pay_changes', people: 6, amount: '23000.00', reason: null },
    { part: 'end', people: 11, amount: '733000.00', reason: null },
  ],
};

/** Five tenure bands, the shortest under five people and the longest empty. */
export const byTenure: InsightPayloads['by-tenure'] = {
  ...USD,
  level: 'all',
  rows: [
    { band: 'under_1', label: 'Under 1 year', headcount: 3, median_gross: null },
    { band: '1_to_3', label: '1 to 3 years', headcount: 8, median_gross: '62500.00' },
    { band: '3_to_5', label: '3 to 5 years', headcount: 6, median_gross: '70000.00' },
    { band: '5_to_10', label: '5 to 10 years', headcount: 10, median_gross: '90000.00' },
    { band: '10_plus', label: '10 years or more', headcount: 0, median_gross: null },
  ],
};

const FEWER_THAN_5 = 'fewer than 5 people';

/** DESIGN 9's shares of total cost: India and the US shown, Germany and the UK short. */
export const costMix: InsightPayloads['cost-mix'] = {
  ...USD,
  view: 'cost',
  segments: [
    { code: 'BASE', name: 'Base salary' },
    { code: 'HRA', name: 'House rent allowance' },
    { code: 'ALLOWANCES', name: 'Allowances' },
    { code: 'BONUS', name: 'Bonus' },
    { code: 'EMPLOYER_CONTRIBUTION', name: 'Employer contribution' },
  ],
  rows: [
    {
      country: { code: 'DE', name: 'Germany' },
      headcount: 4,
      segments: null,
      reason: FEWER_THAN_5,
    },
    {
      country: { code: 'IN', name: 'India' },
      headcount: 12,
      segments: [
        { code: 'BASE', name: 'Base salary', share_pct: '53.6' },
        { code: 'HRA', name: 'House rent allowance', share_pct: '22.3' },
        { code: 'ALLOWANCES', name: 'Allowances', share_pct: '13.4' },
        { code: 'BONUS', name: 'Bonus', share_pct: '0.0' },
        { code: 'EMPLOYER_CONTRIBUTION', name: 'Employer contribution', share_pct: '10.7' },
      ],
      reason: null,
    },
    { country: { code: 'NL', name: 'Netherlands' }, headcount: 0, segments: null, reason: null },
    {
      country: { code: 'SG', name: 'Singapore' },
      headcount: 7,
      segments: null,
      reason: 'Bonus held by fewer than 5 people',
    },
    {
      country: { code: 'GB', name: 'United Kingdom' },
      headcount: 1,
      segments: null,
      reason: FEWER_THAN_5,
    },
    {
      country: { code: 'US', name: 'United States' },
      headcount: 10,
      segments: [
        { code: 'BASE', name: 'Base salary', share_pct: '90.9' },
        { code: 'BONUS', name: 'Bonus', share_pct: '0.0' },
        { code: 'EMPLOYER_CONTRIBUTION', name: 'Employer contribution', share_pct: '9.1' },
      ],
      reason: null,
    },
  ],
};

/** The take-home view of India and the US: net pay and income tax as shares of gross. */
export const costMixTakeHome: InsightPayloads['cost-mix'] = {
  ...USD,
  view: 'take_home',
  segments: [
    { code: 'NET', name: 'Net pay' },
    { code: 'TAX', name: 'Income tax' },
  ],
  rows: [
    {
      country: { code: 'IN', name: 'India' },
      headcount: 12,
      segments: [
        { code: 'NET', name: 'Net pay', share_pct: '90.0' },
        { code: 'TAX', name: 'Income tax', share_pct: '10.0' },
      ],
      reason: null,
    },
    {
      country: { code: 'US', name: 'United States' },
      headcount: 10,
      segments: [
        { code: 'NET', name: 'Net pay', share_pct: '80.0' },
        { code: 'TAX', name: 'Income tax', share_pct: '20.0' },
      ],
      reason: null,
    },
  ],
};

/** Each insight's payload, by the name in its URL, the gender card's for the view it asks for. */
export function insightFor(
  name: string,
  includeExited: boolean,
  view: string | null = null,
): JsonBodyType | undefined {
  const genderViews: Record<string, unknown> = {
    bonus: bonusGap,
    quartiles: quartileGap,
    by_level: levelGapView,
  };
  if (name === 'gender-gap' && view && view in genderViews) {
    return genderViews[view] as JsonBodyType;
  }
  if (name === 'cost-mix' && view === 'take_home') return costMixTakeHome as JsonBodyType;
  const payloads: Record<string, unknown> = {
    summary: includeExited ? summaryWithExited : summary,
    'by-country': byCountry,
    'by-department': byDepartment,
    distribution,
    'by-level': byLevel,
    'gender-gap': genderGap,
    trend,
    'cost-bridge': costBridge,
    'by-tenure': byTenure,
    'cost-mix': costMix,
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
