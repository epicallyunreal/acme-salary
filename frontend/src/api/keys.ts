// TanStack Query keys (DESIGN section 6). Every parameter object is part of its key.

import type { ListParams } from './types';

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
    detail: (id: number) => ['employees', id] as const,
  },
};

/** Meta lookups change only when the owner runs a command, so five minutes is fresh enough. */
export const META_STALE_TIME = 5 * 60 * 1000;
