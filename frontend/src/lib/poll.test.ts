import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ApiError } from '../api/client';
import { mayStillBeRunning, POLL, waitFor } from './poll';

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
