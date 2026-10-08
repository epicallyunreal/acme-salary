// TanStack Query keys (DESIGN section 6). Every parameter object is part of its key.

import type {
  HistoryParams,
  ImportRowParams,
  InsightControl,
  InsightName,
  InsightParams,
  ListParams,
} from './types';

export const keys = {
  me: ['auth', 'me'] as const,
  meta: {
    countries: ['meta', 'countries'] as const,
    departments: ['meta', 'departments'] as const,
    components: (country: string) => ['meta', 'components', country] as const,
    rates: (on?: string) => ['meta', 'rates', on ?? 'today'] as const,
  },
  employees: {
    all: ['employees'] as const,
    list: (params: ListParams) => ['employees', 'list', params] as const,
    /** The detail, the history and the audit list share this prefix, so one invalidation
     * after a write refreshes all three. */
    detail: (id: number) => ['employees', id] as const,
    history: (id: number, params: HistoryParams) =>
      ['employees', id, 'compensation', params] as const,
    audit: (id: number) => ['employees', id, 'audit'] as const,
  },
  insights: {
    all: ['insights'] as const,
    one: (name: InsightName, params: InsightParams, control: InsightControl = {}) =>
      ['insights', name, params, control] as const,
  },
  demo: {
    files: ['demo', 'files'] as const,
    counts: ['demo', 'counts'] as const,
  },
  imports: {
    all: ['imports'] as const,
    lists: ['imports', 'list'] as const,
    list: (page: number) => ['imports', 'list', page] as const,
    /** The batch and its rows share this prefix, so a skip refreshes the summary and the grid. */
    detail: (id: number) => ['imports', id] as const,
    rows: (id: number, params: ImportRowParams) => ['imports', id, 'rows', params] as const,
  },
};

/** Meta lookups change only when the owner runs a command, so five minutes is fresh enough. */
export const META_STALE_TIME = 5 * 60 * 1000;
