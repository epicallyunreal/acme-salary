import { formatMoney } from '../../lib/money';

/** SPEC section 9 withholds pay for a group under five, so one person's pay never shows. */
export const WITHHELD = 'fewer than 5 people';

/** A figure for a table: the amount, `—` for a group with nobody, or why it is withheld. */
export function money(value: string | null, currency: string, headcount: number): string {
  if (value !== null) return formatMoney(value, currency);
  return headcount === 0 ? '—' : WITHHELD;
}
