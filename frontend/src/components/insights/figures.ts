import { formatDate } from '../../lib/dates';
import { formatAmount, formatMoney } from '../../lib/money';
import { todayUtc } from '../../lib/period';

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

/** What a card that groups by level says when its period ends on a day other than today: the
 * level is kept on the employee, so every date reads today's (D64), or null on today. */
export function levelsAsOfToday(to: string, today: string = todayUtc()): string | null {
  if (to === today) return null;
  return `Levels are as of today; anyone promoted after ${formatDate(to)} appears at their new level`;
}

/** A woman's or a man's figure for a table: the amount, `—` for nobody, or `fewer than 5 women`
 * (or men), the gender gap card's words (D62). */
export function genderMoney(
  value: string | null,
  currency: string,
  headcount: number,
  who: 'women' | 'men',
): string {
  if (value !== null) return formatMoney(value, currency);
  return headcount === 0 ? '—' : `fewer than ${SMALL_GROUP} ${who}`;
}

/** What the gender gap card says of itself (D62). */
export const GENDER_NOTE =
  "Follows EU Directive 2023/970 Article 9 and the UK's six gender pay gap measures, on annual pay. Not a statutory filing: no hours, no legal entities.";
export const GAP_FLAG = '5% or more';
export const GAP_FLAG_NOTE =
  '5% or more is the threshold in EU Directive 2023/970 Article 10 for a gap between women and men.';
