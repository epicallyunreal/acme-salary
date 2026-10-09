import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRELOAD_GUARD, pageLoaded, recoverFromPreloadError } from './preloadRecovery';

function preloadError() {
  return new Event('vite:preloadError', { cancelable: true });
}

describe('recoverFromPreloadError', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("reloads once when a page's code has gone, as after a deploy (D78)", () => {
    const reload = vi.fn();
    const event = preloadError();

    recoverFromPreloadError(event, reload);

    expect(reload).toHaveBeenCalledOnce();
    expect(event.defaultPrevented).toBe(true);
    expect(sessionStorage.getItem(PRELOAD_GUARD)).not.toBeNull();
  });

  it('never reloads twice, leaving the error page with its Reload', () => {
    const reload = vi.fn();
    recoverFromPreloadError(preloadError(), reload);
    const again = preloadError();

    recoverFromPreloadError(again, reload);

    expect(reload).toHaveBeenCalledOnce();
    expect(again.defaultPrevented).toBe(false);
  });

  it('may reload again once a page has loaded since, for the next deploy', () => {
    const reload = vi.fn();
    recoverFromPreloadError(preloadError(), reload);

    pageLoaded();
    recoverFromPreloadError(preloadError(), reload);

    expect(reload).toHaveBeenCalledTimes(2);
  });

  it('leaves the error to the page when storage is refused, so it cannot loop', () => {
    const reload = vi.fn();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });

    recoverFromPreloadError(preloadError(), reload);

    expect(reload).not.toHaveBeenCalled();
  });
});
