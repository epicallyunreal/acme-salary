import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router';

import {
  DEFAULT_STATE,
  fromSearchParams,
  type GridState,
  toSearchParams,
  withCurrencyRule,
} from '../grid/serverModel';

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
  const [searchParams, setSearchParams] = useSearchParams();
  const state = useMemo(() => fromSearchParams(searchParams), [searchParams]);

  const set = useCallback(
    (patch: Partial<GridState>) => {
      setSearchParams(
        (current) => toSearchParams(applyChange(fromSearchParams(current), patch)),
        // Typing in the search box should not leave one history entry per keystroke.
        { replace: 'search' in patch },
      );
    },
    [setSearchParams],
  );

  const reset = useCallback(() => {
    setSearchParams(toSearchParams({ ...DEFAULT_STATE, page_size: state.page_size }));
  }, [setSearchParams, state.page_size]);

  return { state, set, reset };
}
