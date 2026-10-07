// Where to send people and how to come back (DESIGN section 6, session handling).

/** The login URL that brings the user back to `location` afterwards. */
export function loginPath(location: { pathname: string; search: string }): string {
  const next = `${location.pathname}${location.search}`;
  return next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`;
}

/** Only a same-origin path is a valid `next`; anything else goes to the start page. */
export function safeNext(next: string | null): string {
  if (next && next.startsWith('/') && !next.startsWith('//')) return next;
  return '/';
}
