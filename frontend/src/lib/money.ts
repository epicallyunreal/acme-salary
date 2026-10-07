// Money arrives from the API as decimal strings and is formatted without ever becoming a float:
// Intl.NumberFormat accepts a numeric string and keeps every digit. Codes, never symbols, because
// six currencies sit in one grid (DESIGN section 7).

const formatters = new Map<string, Intl.NumberFormat>();

function formatter(currency: string, fraction: number, notation: 'standard' | 'compact') {
  const key = `${currency}:${fraction}:${notation}`;
  let cached = formatters.get(key);
  if (!cached) {
    cached = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      currencyDisplay: 'code',
      notation,
      minimumFractionDigits: notation === 'compact' ? 0 : fraction,
      maximumFractionDigits: fraction,
    });
    formatters.set(key, cached);
  }
  return cached;
}

/** `formatMoney('1450000.00', 'INR')` gives `INR 1,450,000`; `{ fraction: 2 }` keeps the cents. */
export function formatMoney(value: string, currency: string, { fraction = 0 } = {}): string {
  return formatter(currency, fraction, 'standard').format(value as Intl.StringNumericLiteral);
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
