import { renderHook } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ApiError } from '../api/client';
import { mayStillBeRunning, POLL, useUnmountSignal, waitFor } from './poll';

describe('mayStillBeRunning', () => {
  it('is true for a network error and for the proxy answering 502 or 504, never for the API', () => {
    expect(mayStillBeRunning(new TypeError('Failed to fetch'))).toBe(true);
    expect(mayStillBeRunning(new ApiError(502, null))).toBe(true);
    expect(mayStillBeRunning(new ApiError(504, null))).toBe(true);
    expect(mayStillBeRunning(new ApiError(409, { detail: 'busy' }))).toBe(false);
    expect(mayStillBeRunning(new ApiError(500, null))).toBe(false);
  });
});

describe('waitFor', () => {
  const defaults = { ...POLL };
  beforeEach(() => {
    POLL.every = 5;
    POLL.upTo = 100;
  });
  afterEach(() => {
    Object.assign(POLL, defaults);
  });

  it('resolves with the first value a check returns, trying again after a throw', async () => {
    let calls = 0;
    const found = await waitFor(async () => {
      calls += 1;
      if (calls === 1) throw new Error('busy');
      return calls >= 3 ? `ready after ${calls}` : null;
    });

    expect(found).toBe('ready after 3');
  });

  it('resolves null once the wait is up', async () => {
    let calls = 0;
    const found = await waitFor(async () => {
      calls += 1;
      return null;
    });

    expect(found).toBeNull();
    expect(calls).toBeGreaterThanOrEqual(2);
  });
});

describe('useUnmountSignal', () => {
  it('fires on unmount, and survives StrictMode running the cleanup an extra time', () => {
    const { result, unmount } = renderHook(() => useUnmountSignal(), { wrapper: StrictMode });
    const signal = result.current();

    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it('stops a wait when the signal fires', async () => {
    POLL.every = 5;
    POLL.upTo = 10000;
    const controller = new AbortController();
    let calls = 0;
    const waiting = waitFor(async () => {
      calls += 1;
      if (calls === 2) controller.abort();
      return null;
    }, controller.signal);

    expect(await waiting).toBeNull();
    expect(calls).toBe(2);
  });
});
