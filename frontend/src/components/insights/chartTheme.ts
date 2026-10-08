import { formatCompact } from '../../lib/money';
import { tokens } from '../../lib/theme';

// DESIGN section 7's mark specs, in one place for the five charts.

/** `[0]` for every single-series chart and the female bars, `[1]` for the male bars. */
export const SERIES = tokens.series;
export const MARKER = tokens.chart.marker;
/** No bar thicker than 24 px, and a 2 px surface gap between adjacent bars. */
export const BAR_SIZE = 24;
export const BAR_GAP = 2;
/** A 4 px rounded data end and a square baseline. */
export const ROUND_RIGHT: [number, number, number, number] = [0, 4, 4, 0];
export const ROUND_TOP: [number, number, number, number] = [4, 4, 0, 0];
export const GRID = { stroke: tokens.chart.grid, strokeWidth: 1 };
export const AXIS = {
  tick: { fill: tokens.inkMuted, fontSize: 12, style: { fontVariantNumeric: 'tabular-nums' } },
  axisLine: false,
  tickLine: false,
} as const;
/** No decorative motion: a chart appears as it is. */
export const STILL = { isAnimationActive: false } as const;
export const CURSOR = { fill: tokens.paper };

/** A money string as a number, for chart geometry only (DESIGN section 6). */
export function plot(value: string | null): number | null {
  return value === null ? null : Number(value);
}

/** An axis tick in the reporting currency: `USD 1.5M`. */
export function compactTick(currency: string) {
  return (value: number) => formatCompact(String(value), currency);
}

/** The cost mix's segments (D62): base and net pay in the first series, bonus and income tax in
 * the second, the employer's contribution in the marker grey, and each country's own component
 * a swatch of its own, so no two segments of a view share one. */
export const MIX_COLORS: Record<string, string> = {
  BASE: tokens.series[0],
  HRA: tokens.mix.ochre,
  ALLOWANCES: tokens.mix.teal,
  HOLIDAY_ALLOWANCE: tokens.mix.plum,
  AWS: tokens.mix.navy,
  BONUS: tokens.series[1],
  EMPLOYER_CONTRIBUTION: tokens.chart.marker,
  NET: tokens.series[0],
  TAX: tokens.series[1],
  NATIONAL_INSURANCE: tokens.mix.teal,
  SOCIAL_INSURANCE: tokens.mix.purple,
  CPF: tokens.mix.brown,
};
/** A component the palette does not know yet. */
export const MIX_OTHER = tokens.mix.other;
