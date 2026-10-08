import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type { InsightControl, InsightName, InsightParams, InsightPayloads } from './types';

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

/** One insight for the dashboard's filters and the card's own control (SPEC section 8). */
export function getInsight<N extends InsightName>(
  name: N,
  params: InsightParams,
  control: InsightControl = {},
): Promise<InsightPayloads[N]> {
  return apiFetch<InsightPayloads[N]>(`/insights/${name}/`, {
    query: { ...insightQuery(params), ...control },
  });
}

/** The filters are part of the key, so a filter change refetches every card, and a card's control
 * is part of its own, so switching it refetches that card alone. The previous figures stay on
 * screen until the new ones arrive. */
export function useInsight<N extends InsightName>(
  name: N,
  params: InsightParams,
  control: InsightControl = {},
) {
  return useQuery({
    queryKey: keys.insights.one(name, params, control),
    queryFn: () => getInsight(name, params, control),
    placeholderData: keepPreviousData,
  });
}
