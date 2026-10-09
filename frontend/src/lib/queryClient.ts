import { QueryClient } from '@tanstack/react-query';

import { ApiError } from '../api/client';

/** No 4xx is retried, since the answer would not change, and a lost connection or a 5xx is
 * retried once (DESIGN section 6, D76). A 401 reaches this only after the client's own refresh
 * has had its one try. */
export function retryOnce(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 1;
}

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: retryOnce, refetchOnWindowFocus: false } },
  });
}
