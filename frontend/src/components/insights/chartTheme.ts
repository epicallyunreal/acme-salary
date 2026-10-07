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
