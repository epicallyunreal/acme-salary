import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import { usePastLastPage } from './usePastLastPage';

const GONE = new ApiError(404, { detail: 'Invalid page.' });

describe('usePastLastPage', () => {
  it('waits for a count page 1 fetched itself, so a cached count of a list that shrank never sends it back (D77)', () => {
    const goTo = vi.fn();
    const { result, rerender } = renderHook((props) => usePastLastPage(props), {
      initialProps: {
        error: GONE as unknown,
        count: undefined as number | undefined,
        fresh: false,
        page: 3,
        pageSize: 10,
        goTo,
      },
    });
    expect(goTo).toHaveBeenLastCalledWith(1);
    // While it is put right the list shows itself loading, not the 404.
    expect(result.current).toBe(true);

    // Page 1 shows the old count of 30 while it fetches: going back to page 3 would loop.
    rerender({ error: null, count: 30, fresh: false, page: 1, pageSize: 10, goTo });
    expect(goTo).toHaveBeenCalledTimes(1);

    // Its own count says one page is left, so it stays where it is.
    rerender({ error: null, count: 10, fresh: true, page: 1, pageSize: 10, goTo });
    expect(goTo).toHaveBeenCalledTimes(1);
    expect(result.current).toBe(false);
  });

  it('goes to the last page once page 1 has its own count', () => {
    const goTo = vi.fn();
    const { rerender } = renderHook((props) => usePastLastPage(props), {
      initialProps: {
        error: GONE as unknown,
        count: undefined as number | undefined,
        fresh: false,
        page: 9,
        pageSize: 10,
        goTo,
      },
    });
    rerender({ error: null, count: 45, fresh: true, page: 1, pageSize: 10, goTo });

    expect(goTo.mock.calls).toEqual([[1], [5]]);
  });
});
