// Where to send people and how to come back (DESIGN section 6, session handling).

/** The login URL that brings the user back to `location` afterwards. */
export function loginPath(location: { pathname: string; search: string }): string {
  // Several requests can fail together; the first redirect carries the page, the rest stay put.
  if (location.pathname === '/login') return `${location.pathname}${location.search}`;
  const next = `${location.pathname}${location.search}`;
  return next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`;
}

/**
 * Only a same-origin path is a valid `next`; anything else goes to the start page. The value is
 * resolved by the URL parser, which is what the browser would do with it, so a backslash, a tab
 * or a newline cannot smuggle another host past a prefix check.
 */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith('/')) return '/';
  let url: URL;
  try {
    url = new URL(next, window.location.origin);
  } catch {
    return '/';
  }
  if (url.origin !== window.location.origin) return '/';
  return `${url.pathname}${url.search}${url.hash}`;
}
