// The session (DESIGN section 6, DECISIONS D21): the access token lives in memory behind a tiny
// external store, the refresh token in localStorage. One refresh is ever in flight at a time.

import { useSyncExternalStore } from 'react';

import { apiUrl, REFRESH_STORAGE_KEY } from './constants';

export interface Tokens {
  access: string;
  refresh: string;
}

let accessToken: string | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setSession(tokens: Tokens) {
  accessToken = tokens.access;
  try {
    localStorage.setItem(REFRESH_STORAGE_KEY, tokens.refresh);
  } catch {
    // Private mode or blocked storage: the session then lasts as long as the access token.
  }
  emit();
}

export function clearSession() {
  accessToken = null;
  try {
    localStorage.removeItem(REFRESH_STORAGE_KEY);
  } catch {
    // Nothing to remove.
  }
  emit();
}

/** Re-renders when the access token appears or disappears. */
export function useAccessToken(): string | null {
  return useSyncExternalStore(subscribe, getAccessToken, getAccessToken);
}

let inflight: Promise<boolean> | null = null;

async function refresh(): Promise<boolean> {
  const token = getRefreshToken();
  if (!token) return false;
  let response: Response;
  try {
    response = await fetch(apiUrl('/auth/refresh/'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: token }),
    });
  } catch {
    return false;
  }
  if (!response.ok) {
    clearSession();
    return false;
  }
  const data = (await response.json()) as { access: string; refresh?: string };
  // Rotation returns a new refresh token; keep the old one only if the server did not.
  setSession({ access: data.access, refresh: data.refresh ?? token });
  return true;
}

/**
 * Refreshes the access token once, however many callers ask while it is in flight.
 * Resolves true when a new access token is in place.
 */
export function refreshOnce(): Promise<boolean> {
  if (!inflight) {
    inflight = refresh().finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

/** On load: one refresh when a refresh token is stored, otherwise the app starts signed out. */
export async function bootstrap(): Promise<void> {
  if (getRefreshToken()) await refreshOnce();
}
