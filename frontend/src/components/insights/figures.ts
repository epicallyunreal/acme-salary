import { formatAmount, formatMoney } from '../../lib/money';

/** SPEC section 9 and D59: under five people a group shows its headcount alone, and the spread
 * figures (p10 to p90, the distribution) need twenty. The API withholds the figures; these name
 * the rule on screen. */
export const SMALL_GROUP = 5;
export const SPREAD_GROUP = 20;

export function withheld(need: number = SMALL_GROUP): string {
  return `fewer than ${need} people`;
}

/** A figure for a table: the amount, `—` for a group with nobody, or why it is withheld. */
export function money(
  value: string | null,
  currency: string,
  headcount: number,
  need: number = SMALL_GROUP,
): string {
  if (value !== null) return formatMoney(value, currency);
  return headcount === 0 ? '—' : withheld(need);
}

/** A share of total cost: `65.5%`, `—` for nobody, or why it is withheld. */
export function share(value: string | null, headcount: number): string {
  if (value !== null) return `${value}%`;
  return headcount === 0 ? '—' : withheld();
}

export function people(count: number): string {
  return `${formatAmount(String(count))} ${count === 1 ? 'person' : 'people'}`;
}

/** A headcount for a table cell, with thousands separators. */
export function count(value: number): string {
  return formatAmount(String(value));
}

/** What `trend` and `cost-bridge` say while Include exited is ticked: they count the people
 * employed on each date, the one exception to the bar deciding who is counted (D62). */
export const EMPLOYED_ON_EACH_DATE =
  "Counts people employed on each date; Include exited doesn't apply";
