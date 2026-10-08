// Dates arrive as ISO strings. A date-only value is built from its parts so the browser's time
// zone never shifts it to the previous day. Months are three letters, `Sep` as well, which
// en-GB's own short month writes `Sept` (D62).

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function twoDigits(value: number): string {
  return String(value).padStart(2, '0');
}

function dayMonthYear(day: Date): string {
  return `${day.getDate()} ${MONTHS[day.getMonth()]} ${day.getFullYear()}`;
}

export function parseIsoDate(value: string): Date {
  const [year, month, day] = value.slice(0, 10).split('-').map(Number);
  return new Date(year, month - 1, day);
}

/** `formatDate('2026-10-07')` gives `7 Oct 2026`. Null and empty give an empty string. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '';
  return dayMonthYear(parseIsoDate(value));
}

/** A date on a chart's axis: a month-end as `Sep 2026`, and any other day, the period's first or
 * last where it is not a month-end, as `7 Oct 2025`. The year is written in full, so no month
 * reads as a day (D69). */
export function formatAxisDate(value: string): string {
  const day = parseIsoDate(value);
  const next = new Date(day.getFullYear(), day.getMonth(), day.getDate() + 1);
  return next.getDate() === 1
    ? `${MONTHS[day.getMonth()]} ${day.getFullYear()}`
    : dayMonthYear(day);
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
  return `${day.getFullYear()}-${twoDigits(day.getMonth() + 1)}-${twoDigits(day.getDate())}`;
}

/** `formatDateTime('2026-10-07T09:00:00Z')` gives the instant in the viewer's zone, e.g. `7 Oct 2026, 14:30`. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '';
  const instant = new Date(value);
  return `${dayMonthYear(instant)}, ${twoDigits(instant.getHours())}:${twoDigits(instant.getMinutes())}`;
}
