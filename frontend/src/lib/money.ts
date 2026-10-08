// Money arrives from the API as decimal strings and is formatted without ever becoming a float:
// Intl.NumberFormat accepts a numeric string and keeps every digit. Codes, never symbols, because
// six currencies sit in one grid (DESIGN section 7).

const formatters = new Map<string, Intl.NumberFormat>();

function formatter(
  currency: string,
  fraction: number,
  notation: 'standard' | 'compact',
  signDisplay: 'auto' | 'exceptZero' = 'auto',
) {
  const key = `${currency}:${fraction}:${notation}:${signDisplay}`;
  let cached = formatters.get(key);
  if (!cached) {
    cached = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      currencyDisplay: 'code',
      notation,
      signDisplay,
      minimumFractionDigits: notation === 'compact' ? 0 : fraction,
      maximumFractionDigits: fraction,
    });
    formatters.set(key, cached);
  }
  return cached;
}

/** `formatMoney('1450000.00', 'INR')` gives `INR 1,450,000`; `{ fraction: 2 }` keeps the cents.
 * `{ signed: true }` writes a change: `+USD 23,000`, `-USD 6,250`, and `USD 0` for none. */
export function formatMoney(
  value: string,
  currency: string,
  { fraction = 0, signed = false } = {},
): string {
  const sign = signed ? 'exceptZero' : 'auto';
  return formatter(currency, fraction, 'standard', sign).format(value as Intl.StringNumericLiteral);
}

const amountFormatters = new Map<number, Intl.NumberFormat>();

/** The figure without its code, for layouts that set the code apart: `2,392,500`. */
export function formatAmount(value: string, { fraction = 0 } = {}): string {
  let cached = amountFormatters.get(fraction);
  if (!cached) {
    cached = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: fraction,
      maximumFractionDigits: fraction,
    });
    amountFormatters.set(fraction, cached);
  }
  return cached.format(value as Intl.StringNumericLiteral);
}

/** True for `0`, `0.00` and the like, read from the string so no float is involved. */
export function isZero(value: string): boolean {
  return /^0*(\.0*)?$/.test(value);
}

/** An FX rate as stored, eight places, without its trailing zeros: `0.01200000` gives `0.012`. */
export function formatRate(rate: string): string {
  return rate.includes('.') ? rate.replace(/0+$/, '').replace(/\.$/, '') : rate;
}

const compactAmount = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

/** `2.4M` without its code, for a KPI figure set beside the code (DESIGN section 7). */
export function formatCompactAmount(value: string): string {
  return compactAmount.format(value as Intl.StringNumericLiteral);
}

/** `USD 1.2M` for chart axes and KPI cards. */
export function formatCompact(value: string, currency: string): string {
  return formatter(currency, 1, 'compact').format(value as Intl.StringNumericLiteral);
}

/** The annual figure divided by twelve, exact to the cent and rounded half up, as a decimal
 * string for `formatMoney`. Integer arithmetic on cents, so no float touches the money. */
export function monthly(value: string): string {
  const [whole, fraction = ''] = value.split('.');
  const cents = BigInt(whole) * 100n + BigInt((fraction + '00').slice(0, 2));
  const twelfth = cents / 12n;
  const rounded = (cents % 12n) * 2n >= 12n ? twelfth + 1n : twelfth;
  return `${rounded / 100n}.${(rounded % 100n).toString().padStart(2, '0')}`;
}
