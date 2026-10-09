import { reloadPage } from './navigation';

// After a deploy the old chunk files are gone, so a tab opened before it fails to load a page it
// has not visited yet. Vite says so with `vite:preloadError`. The page reloads once, onto the new
// build, and the guard in sessionStorage stops a second reload, so the error page with its Reload
// stays when the failure is something else (D78).
export const PRELOAD_GUARD = 'acme.preload-reload';

export function recoverFromPreloadError(event: Event, reload: () => void = reloadPage) {
  try {
    if (sessionStorage.getItem(PRELOAD_GUARD) !== null) return;
    sessionStorage.setItem(PRELOAD_GUARD, '1');
  } catch {
    return; // no storage, no guard: the error page stays rather than risk a loop
  }
  event.preventDefault();
  reload();
}

/** A page loaded, so a later deploy may reload once again. */
export function pageLoaded() {
  try {
    sessionStorage.removeItem(PRELOAD_GUARD);
  } catch {
    // nothing to clear
  }
}
