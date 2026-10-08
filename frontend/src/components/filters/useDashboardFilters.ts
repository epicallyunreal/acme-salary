import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import type { InsightParams } from '../../api/types';
import { REPORTING_CURRENCIES } from '../../lib/constants';
import {
  customPeriod,
  DEFAULT_PERIOD,
  type PeriodName,
  PERIODS,
  type PresetName,
  presetPeriod,
  todayUtc,
} from '../../lib/period';
import { csv, oneOf, withCurrencyRule } from '../grid/serverModel';

/** The dashboard's filters (SPEC F5), in the URL so a view is a link: who is counted, in which
 * currency, and over which period, a preset's name or `custom` with its dates (D64). */
export interface DashboardFilters extends InsightParams {
  period: PeriodName;
}

/** Everyone, in USD, without the people who have left, over the last 12 months. */
export const DASHBOARD_DEFAULTS = {
  country: [] as string[],
  department: [] as string[],
  currency: 'usd',
  include_exited: false,
  period: DEFAULT_PERIOD,
} satisfies Omit<DashboardFilters, 'from' | 'to'>;

/** The defaults with the default period's dates, worked out against `today`. */
export function defaultFilters(today: string = todayUtc()): DashboardFilters {
  return { ...DASHBOARD_DEFAULTS, ...presetPeriod(DEFAULT_PERIOD, today) };
}

/** The filters as the insights take them: the period's dates without its name, so a preset and a
 * custom range of the same dates are one query. */
export function insightParams(filters: DashboardFilters): InsightParams {
  const { country, department, currency, include_exited, from, to } = filters;
  return { country, department, currency, include_exited, from, to };
}

/** Each card's own control (D62), in the URL under the card's prefix, the first value the default.
 * It slices or measures and never decides who is counted. */
export const CARD_CONTROLS = {
  trend: { key: 'trend.measure', param: 'measure', values: ['total_cost', 'headcount'] },
  mix: { key: 'mix.view', param: 'view', values: ['cost', 'take_home'] },
  gap: {
    key: 'gap.view',
    param: 'view',
    values: ['pay_gap', 'bonus', 'quartiles', 'by_level'],
  },
  tenure: {
    key: 'tenure.level',
    param: 'level',
    values: ['all', '1', '2', '3', '4', '5', '6'],
  },
} as const;

export type CardName = keyof typeof CARD_CONTROLS;
export type CardControls = { [card in CardName]: (typeof CARD_CONTROLS)[card]['values'][number] };

const CARDS = Object.keys(CARD_CONTROLS) as CardName[];

/** The card controls the URL names, each falling back to its default. */
export function controlsFromSearchParams(params: URLSearchParams): CardControls {
  return Object.fromEntries(
    CARDS.map((card) => {
      const { key, values } = CARD_CONTROLS[card];
      return [card, oneOf(params.get(key), values, values[0])];
    }),
  ) as CardControls;
}

/** A card's control as its insight and its export take it: `{ measure: 'headcount' }`. */
export function controlQuery(card: CardName, controls: CardControls): Record<string, string> {
  return { [CARD_CONTROLS[card].param]: controls[card] };
}

/** Reads the URL; anything malformed falls back to the default. `local` needs one country, and a
 * preset's dates are worked out against `today`, so a shared link stays relative (D64). */
export function dashboardFromSearchParams(
  params: URLSearchParams,
  today: string = todayUtc(),
): DashboardFilters {
  const named = oneOf(params.get('period'), PERIODS, DASHBOARD_DEFAULTS.period);
  const custom = named === 'custom' ? customPeriod(params.get('from'), params.get('to')) : null;
  const preset: PresetName = named === 'custom' ? DASHBOARD_DEFAULTS.period : named;
  return withCurrencyRule({
    country: csv(params.get('country')),
    department: csv(params.get('department')),
    currency: oneOf(params.get('currency'), REPORTING_CURRENCIES, DASHBOARD_DEFAULTS.currency),
    include_exited: params.get('include_exited') === 'true',
    period: custom ? 'custom' : preset,
    ...(custom ?? presetPeriod(preset, today)),
  });
}

/** Writes the URL, leaving out the defaults so links stay short. */
export function dashboardToSearchParams(
  filters: DashboardFilters,
  controls: CardControls = controlsFromSearchParams(new URLSearchParams()),
): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.country.length) params.set('country', filters.country.join(','));
  if (filters.department.length) params.set('department', filters.department.join(','));
  if (filters.currency !== DASHBOARD_DEFAULTS.currency) params.set('currency', filters.currency);
  if (filters.include_exited) params.set('include_exited', 'true');
  if (filters.period !== DASHBOARD_DEFAULTS.period) params.set('period', filters.period);
  if (filters.period === 'custom') {
    params.set('from', filters.from);
    params.set('to', filters.to);
  }
  for (const card of CARDS) {
    const { key, values } = CARD_CONTROLS[card];
    if (controls[card] !== values[0]) params.set(key, controls[card]);
  }
  return params;
}

export function useDashboardFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => dashboardFromSearchParams(searchParams), [searchParams]);
  const params = useMemo(() => insightParams(filters), [filters]);
  const controls = useMemo(() => controlsFromSearchParams(searchParams), [searchParams]);

  const set = useCallback(
    (patch: Partial<DashboardFilters>) =>
      setSearchParams((current) =>
        dashboardToSearchParams(
          withCurrencyRule({ ...dashboardFromSearchParams(current), ...patch }),
          controlsFromSearchParams(current),
        ),
      ),
    [setSearchParams],
  );
  const setControl = useCallback(
    <C extends CardName>(card: C, value: CardControls[C]) =>
      setSearchParams((current) =>
        dashboardToSearchParams(dashboardFromSearchParams(current), {
          ...controlsFromSearchParams(current),
          [card]: value,
        }),
      ),
    [setSearchParams],
  );
  // Clear filters resets the card controls and the period with the bar's filters (D62, D64).
  const reset = useCallback(() => setSearchParams(new URLSearchParams()), [setSearchParams]);
  const filtered = dashboardToSearchParams(filters, controls).size > 0;

  return { filters, params, controls, set, setControl, reset, filtered };
}
