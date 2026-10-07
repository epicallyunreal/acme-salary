import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type { InsightName, InsightParams, InsightPayloads } from './types';

/** The dashboard's filters on the wire, for an insight and for its export. The UI never sends
 * `on`, so the API reports on today (DESIGN section 6). */
export function insightQuery(params: InsightParams) {
  return {
    country: params.country,
    department: params.department,
    currency: params.currency,
    include_exited: params.include_exited ? 'true' : undefined,
  };
}

/** One insight for the dashboard's filters (SPEC section 8). */
export function getInsight<N extends InsightName>(
  name: N,
  params: InsightParams,
): Promise<InsightPayloads[N]> {
  return apiFetch<InsightPayloads[N]>(`/insights/${name}/`, { query: insightQuery(params) });
}

/** The filters are part of the key, so a filter change refetches every card; the previous
 * figures stay on screen until the new ones arrive. */
export function useInsight<N extends InsightName>(name: N, params: InsightParams) {
  return useQuery({
    queryKey: keys.insights.one(name, params),
    queryFn: () => getInsight(name, params),
    placeholderData: keepPreviousData,
  });
}
