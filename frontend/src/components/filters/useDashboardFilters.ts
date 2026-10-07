import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import type { InsightParams, ReportingCurrency } from '../../api/types';
import { csv, withCurrencyRule } from '../grid/serverModel';

/** The dashboard's filters (SPEC F5), in the URL so a view is a link. */
export type DashboardFilters = InsightParams;

export const DASHBOARD_DEFAULTS: DashboardFilters = {
  country: [],
  department: [],
  currency: 'usd',
  include_exited: false,
};

const CURRENCIES: ReadonlySet<string> = new Set(['usd', 'eur', 'local']);

/** Reads the URL; anything malformed falls back to the default. `local` needs one country. */
export function dashboardFromSearchParams(params: URLSearchParams): DashboardFilters {
  const currency = params.get('currency') ?? '';
  return withCurrencyRule({
    country: csv(params.get('country')),
    department: csv(params.get('department')),
    currency: (CURRENCIES.has(currency) ? currency : 'usd') as ReportingCurrency,
    include_exited: params.get('include_exited') === 'true',
  });
}

/** Writes the URL, leaving out the defaults so links stay short. */
export function dashboardToSearchParams(filters: DashboardFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.country.length) params.set('country', filters.country.join(','));
  if (filters.department.length) params.set('department', filters.department.join(','));
  if (filters.currency !== 'usd') params.set('currency', filters.currency);
  if (filters.include_exited) params.set('include_exited', 'true');
  return params;
}

export function useDashboardFilters() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => dashboardFromSearchParams(searchParams), [searchParams]);

  const set = useCallback(
    (patch: Partial<DashboardFilters>) =>
      setSearchParams((current) =>
        dashboardToSearchParams(
          withCurrencyRule({ ...dashboardFromSearchParams(current), ...patch }),
        ),
      ),
    [setSearchParams],
  );
  const reset = useCallback(() => setSearchParams(new URLSearchParams()), [setSearchParams]);
  const filtered = dashboardToSearchParams(filters).size > 0;

  return { filters, set, reset, filtered };
}
