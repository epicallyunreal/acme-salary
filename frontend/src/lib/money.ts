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

/** The annual figure divided by twelve, for the "per month" line on the detail card. Display only. */
export function monthly(value: string, currency: string): string {
  return formatMoney((Number(value) / 12).toFixed(2), currency);
}
