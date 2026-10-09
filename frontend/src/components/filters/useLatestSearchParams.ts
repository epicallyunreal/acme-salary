import { useCallback, useLayoutEffect, useRef } from 'react';
import { type NavigateOptions, useSearchParams } from 'react-router';

/** `useSearchParams` with an updater that builds the next URL from the latest one (D76). React
 * Router 8.4's setter hands its updater the params of the render that made it, so a callback that
 * outlives a render, a debounced commit first, would write back a URL from before a later change,
 * Clear filters among them. The latest params live in a ref, refreshed after each render and on
 * each write. */
export function useLatestSearchParams() {
  const [searchParams, setSearchParams] = useSearchParams();
  const latest = useRef(searchParams);
  useLayoutEffect(() => {
    latest.current = searchParams;
  }, [searchParams]);

  const update = useCallback(
    (next: (current: URLSearchParams) => URLSearchParams, options?: NavigateOptions) => {
      const params = next(new URLSearchParams(latest.current));
      latest.current = params;
      setSearchParams(params, options);
    },
    [setSearchParams],
  );

  return [searchParams, update] as const;
}
