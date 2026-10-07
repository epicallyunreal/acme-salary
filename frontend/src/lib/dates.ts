// Dates arrive as ISO strings. A date-only value is built from its parts so the browser's time
// zone never shifts it to the previous day.

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});
const dateTimeFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export function parseIsoDate(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  return new Date(year, month - 1, day);
}

/** `formatDate('2026-10-07')` gives `7 Oct 2026`. Null and empty give an empty string. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '';
  return dateFormat.format(parseIsoDate(value));
}

const monthFormat = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric' });

/** `formatMonth('2026-10-01')` gives `October 2026`, the name of a month's rates. */
export function formatMonth(value: string | null | undefined): string {
  if (!value) return '';
  return monthFormat.format(parseIsoDate(value));
}

/** The ISO date one day earlier. A record's `effective_to` is exclusive, so its last day is the
 * day before: `dayBefore('2026-04-01')` gives `2026-03-31`. */
export function dayBefore(value: string): string {
  const day = parseIsoDate(value);
  day.setDate(day.getDate() - 1);
  const month = String(day.getMonth() + 1).padStart(2, '0');
  return `${day.getFullYear()}-${month}-${String(day.getDate()).padStart(2, '0')}`;
}

/** `formatDateTime('2026-10-07T09:00:00Z')` gives the instant in the viewer's zone, e.g. `7 Oct 2026, 14:30`. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '';
  return dateTimeFormat.format(new Date(value));
}
