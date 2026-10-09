import { useEffect, useRef } from 'react';

import { ApiError } from '../../api/client';

interface PastLastPage {
  /** The list query's error: the API answers a page past the last with a 404. */
  error: unknown;
  /** The list's count, once a page of it has loaded. */
  count: number | undefined;
  /** True when the count is the page's own answer, not the previous page's kept on screen or a
   * cached one being fetched again: a list that shrank under an open page must not be counted
   * from before it shrank, or the hook would send it back to the page that is gone. */
  fresh: boolean;
  page: number;
  pageSize: number;
  /** Goes to a page with the URL replaced. */
  goTo: (page: number) => void;
}

/** A link to a page past the last, an old one or one to a list that has shrunk, opens the last
 * page with the URL replaced, as Go to page does, and says nothing (D77). The first page's own
 * count, fetched after the move, is the one the last is worked out from. Returns true while the
 * page is being put right, so the list shows itself loading rather than an error. */
export function usePastLastPage({
  error,
  count,
  fresh,
  page,
  pageSize,
  goTo,
}: PastLastPage): boolean {
  const finding = useRef(false);
  const past = error instanceof ApiError && error.status === 404 && page > 1;

  useEffect(() => {
    if (!past) return;
    finding.current = true;
    goTo(1);
  }, [past, goTo]);

  useEffect(() => {
    if (!finding.current || page !== 1 || count === undefined || !fresh) return;
    finding.current = false;
    const last = Math.max(1, Math.ceil(count / pageSize));
    if (last > 1) goTo(last);
  }, [page, count, fresh, pageSize, goTo]);

  return past;
}
