import { useCallback, useMemo } from 'react';

import {
  DEFAULT_STATE,
  fromSearchParams,
  type GridState,
  toSearchParams,
  withCurrencyRule,
} from '../grid/serverModel';
import { useLatestSearchParams } from './useLatestSearchParams';

const PAGING_KEYS: ReadonlySet<keyof GridState> = new Set(['page', 'page_size', 'ordering']);

/**
 * Applies a change to the URL state (DESIGN section 6). Any filter change goes back to page 1,
 * and `local` only stays the currency while exactly one country is selected.
 */
export function applyChange(state: GridState, patch: Partial<GridState>): GridState {
  const next = { ...state, ...patch };
  const touchesFilter = (Object.keys(patch) as (keyof GridState)[]).some(
    (key) => !PAGING_KEYS.has(key),
  );
  if (touchesFilter && patch.page === undefined) next.page = 1;
  return withCurrencyRule(next);
}

/** The directory's filters, page, sort and search, read from and written to the URL. */
export function useUrlFilters() {
  const [searchParams, update] = useLatestSearchParams();
  const state = useMemo(() => fromSearchParams(searchParams), [searchParams]);

  const set = useCallback(
    (patch: Partial<GridState>) => {
      update(
        (current) => toSearchParams(applyChange(fromSearchParams(current), patch)),
        // Typing in the search box should not leave one history entry per keystroke.
        { replace: 'search' in patch },
      );
    },
    [update],
  );

  // Clear filters clears the filters and the search alone: the sort and the page size stay, and
  // the page goes back to the first (D63).
  const reset = useCallback(() => {
    update((current) => {
      const { ordering, page_size } = fromSearchParams(current);
      return toSearchParams({ ...DEFAULT_STATE, ordering, page_size });
    });
  }, [update]);

  return { state, set, reset };
}
