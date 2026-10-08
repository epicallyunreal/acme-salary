// Waiting through a cut connection (DESIGN section 6, D72). Fly's proxy closes a connection that
// carries no data for 60 s, and a threaded gunicorn worker learns of it only when it writes the
// response, so an upload, an approve or a reset cut that way still finishes on the server. The
// page keeps its in-progress state and polls for the result instead of giving up.

import { useCallback, useEffect, useRef } from 'react';

import { ApiError } from '../api/client';

/** How often to look, and for how long, before saying the server may still be working. Tests
 * shorten both. */
export const POLL = { every: 5000, upTo: 600000 };

/** Whether a failed request may still be running on the server: a network error, or a 502 or
 * 504, which is how a cut request reaches the page. Any answer the API itself gave is final. */
export function mayStillBeRunning(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 502 || error.status === 504;
}

/** Calls `check` every `POLL.every` ms until it returns a value, and resolves with it, or
 * resolves null once `POLL.upTo` ms have passed or `signal` is aborted, which a page does when
 * it unmounts, so nothing polls after a sign-out. A check that throws is tried again. */
export function waitFor<T>(
  check: () => Promise<T | null | undefined>,
  signal?: AbortSignal,
): Promise<T | null> {
  const deadline = Date.now() + POLL.upTo;
  return new Promise((resolve) => {
    const attempt = async () => {
      if (signal?.aborted) {
        resolve(null);
        return;
      }
      try {
        const found = await check();
        if (found !== null && found !== undefined) {
          resolve(found);
          return;
        }
      } catch {
        // The server may be busy or the connection down; the next attempt asks again.
      }
      if (Date.now() >= deadline || signal?.aborted) {
        resolve(null);
        return;
      }
      setTimeout(() => void attempt(), POLL.every);
    };
    setTimeout(() => void attempt(), POLL.every);
  });
}

/** A getter for a signal that fires when the component unmounts, read as a `waitFor` starts.
 * The controller is made in the effect and made again after each cleanup, since React's
 * StrictMode runs the cleanup once extra in development. */
export function useUnmountSignal(): () => AbortSignal {
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    return () => {
      current.abort();
      controller.current = null;
    };
  }, []);
  return useCallback(() => (controller.current ??= new AbortController()).signal, []);
}
