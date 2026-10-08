import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Typography,
} from '@mui/material';
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError } from '../../api/client';
import { mayStillBeRunning, useUnmountSignal, waitFor } from '../../lib/poll';
import type { FormMessage } from '../forms/applyServerErrors';
import {
  type BusyApi,
  BusyContext,
  type BusyOptions,
  type BusyPhase,
  type BusyResult,
  type BusyState,
} from './busyContext';

/** After this long the dialog says why it may be slow. */
const SLOW_AFTER_SECONDS = 20;
const SLOW = 'The demo runs on a small shared machine; this can take a few minutes.';
const STILL_WORKING = 'Still working\u2026';
const CUT =
  'The connection was cut before the server answered. Check your connection and try again.';
const GAVE_UP = 'The server may still be working. Reload the page and check.';

/** The one dialog every request the server finishes on its own runs behind (D72): modal, with
 * no way to dismiss it while the request is pending, a prompt before the page is left, the time
 * elapsed, and the refusal in its place when there is one. */
export function BusyProvider({ children }: { children: ReactNode }) {
  const [busy, setBusy] = useState<BusyState | null>(null);
  // Read when a run starts, so a second one cannot open over the first.
  const open = useRef(false);
  const unmountSignal = useUnmountSignal();

  const close = useCallback(() => {
    open.current = false;
    setBusy(null);
  }, []);

  const run = useCallback(
    async <T,>(
      title: string,
      task: () => Promise<T>,
      options: BusyOptions<T>,
    ): Promise<BusyResult<T>> => {
      if (open.current) return { ok: false };
      open.current = true;
      const startedAt = Date.now();
      const show = (phase: BusyPhase, messages: FormMessage[] = []) =>
        setBusy({
          title: phase === 'failed' ? options.failedTitle : title,
          startedAt,
          phase,
          messages,
        });
      const fail = (messages: FormMessage[], error?: unknown): BusyResult<T> => {
        show('failed', messages);
        return { ok: false, error };
      };
      const finish = (value: T): BusyResult<T> => {
        const refusal = options.refusal?.(value) ?? null;
        if (refusal) return fail(refusal);
        close();
        return { ok: true, value };
      };
      show('pending');
      try {
        return finish(await task());
      } catch (error) {
        if (error instanceof ApiError && !mayStillBeRunning(error)) {
          const problems = options.problems?.(error) ?? [
            { key: null, message: error.detail() ?? `Error ${error.status}` },
          ];
          return fail(problems, error);
        }
        if (!options.recover) return fail([{ key: null, message: options.cut ?? CUT }], error);
        // The proxy cut the request, but the server works on: look for its result (D72).
        show('polling');
        const signal = unmountSignal();
        const found = await waitFor(options.recover, signal);
        if (signal.aborted) return { ok: false, error };
        if (found === null) return fail([{ key: null, message: options.gaveUp ?? GAVE_UP }], error);
        return finish(found);
      }
    },
    [close, unmountSignal],
  );

  const api = useMemo<BusyApi>(() => ({ busy, run }), [busy, run]);

  return (
    <BusyContext.Provider value={api}>
      {children}
      <BusyDialog busy={busy} onClose={close} />
    </BusyContext.Provider>
  );
}

/** Whole seconds since `startedAt`, ticking once a second, 0 when nothing is running. */
function useElapsedSeconds(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
}

function BusyDialog({ busy, onClose }: { busy: BusyState | null; onClose: () => void }) {
  // The last state shown stays through the closing fade.
  const [shown, setShown] = useState(busy);
  if (busy && busy !== shown) setShown(busy);
  const pending = busy !== null && busy.phase !== 'failed';
  const failed = shown?.phase === 'failed';
  const elapsed = useElapsedSeconds(pending ? busy.startedAt : null);

  // Leaving the page would lose the result, not stop the server: the browser asks first.
  useEffect(() => {
    if (!pending) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pending]);

  return (
    <Dialog
      open={busy !== null}
      // Escape and the backdrop close nothing while the request is pending (MUI 9 has no
      // disableEscapeKeyDown: the reason is checked instead).
      onClose={() => {
        if (failed) onClose();
      }}
      aria-labelledby="busy-title"
      fullWidth
      maxWidth="xs"
    >
      <DialogTitle id="busy-title">{shown?.title}</DialogTitle>
      <DialogContent>
        {failed ? (
          <Alert severity="error" variant="outlined">
            <Box component="ul" sx={{ m: 0, pl: 4 }}>
              {shown.messages.map(({ message }, index) => (
                <li key={index}>{message}</li>
              ))}
            </Box>
          </Alert>
        ) : (
          <>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <CircularProgress size={24} aria-hidden />
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {elapsed} s elapsed
              </Typography>
            </Box>
            {shown?.phase === 'polling' ? (
              <DialogContentText role="status" sx={{ mt: 3 }}>
                {STILL_WORKING}
              </DialogContentText>
            ) : null}
            {elapsed >= SLOW_AFTER_SECONDS ? (
              <DialogContentText sx={{ mt: 3 }}>{SLOW}</DialogContentText>
            ) : null}
          </>
        )}
      </DialogContent>
      {failed ? (
        <DialogActions>
          <Button onClick={onClose} autoFocus>
            Close
          </Button>
        </DialogActions>
      ) : null}
    </Dialog>
  );
}
