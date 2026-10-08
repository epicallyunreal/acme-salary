import { createContext, useContext } from 'react';

import type { ApiError } from '../../api/client';
import type { FormMessage } from '../forms/applyServerErrors';

/** What a request the server finishes on its own needs beyond its task (D72). */
export interface BusyOptions<T> {
  /** The dialog's title once the request has failed: "The file was not staged". */
  failedTitle: string;
  /** The refusal's messages; the API's detail, or its status, by default. */
  problems?: (error: ApiError) => FormMessage[];
  /** On a cut connection, looks for the result the server made; null means not yet. Without
   * it, a cut connection is a failure that says `cut`. */
  recover?: () => Promise<T | null>;
  /** What to say after ten minutes of looking. */
  gaveUp?: string;
  /** What to say when the connection was cut and there is nothing to look for. */
  cut?: string;
  /** A result that is a refusal after all, such as a batch that ended failed, with what to say. */
  refusal?: (value: T) => FormMessage[] | null;
}

export type BusyPhase = 'pending' | 'polling' | 'failed';

export interface BusyState {
  title: string;
  startedAt: number;
  phase: BusyPhase;
  /** The failure's messages, once failed. */
  messages: FormMessage[];
}

export type BusyResult<T> = { ok: true; value: T } | { ok: false; error?: unknown };

export interface BusyApi {
  /** The action in progress, or null. Buttons that start one are off while it is set. */
  busy: BusyState | null;
  /** Runs `task` behind the dialog and resolves once it is over: the value with the dialog
   * closed, or not ok with the dialog showing why, until its Close button is pressed. */
  run<T>(title: string, task: () => Promise<T>, options: BusyOptions<T>): Promise<BusyResult<T>>;
}

export const BusyContext = createContext<BusyApi | null>(null);

export function useBusy(): BusyApi {
  const api = useContext(BusyContext);
  if (api === null) throw new Error('useBusy needs a BusyProvider above it');
  return api;
}
