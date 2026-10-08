// The dashboard's period (SPEC F5, D64). Dates are ISO strings worked out from their parts, so
// neither the browser's time zone nor a short month moves them.

import { FY_START, PERIOD_LAST, REPORTING_START } from './constants';
import { dayBefore, formatDate } from './dates';

/** The bar's presets and Custom, in menu order, each a name the URL keeps. */
export const PERIODS = [
  'last_3_months',
  'last_6_months',
  'last_12_months',
  'fy_to_date',
  'last_fy',
  'custom',
] as const;
export type PeriodName = (typeof PERIODS)[number];
export type PresetName = Exclude<PeriodName, 'custom'>;

export const DEFAULT_PERIOD: PresetName = 'last_12_months';

export const PERIOD_LABELS: Record<PeriodName, string> = {
  last_3_months: 'Last 3 months',
  last_6_months: 'Last 6 months',
  last_12_months: 'Last 12 months',
  fy_to_date: 'Current FY to date',
  last_fy: 'Last FY',
  custom: 'Custom',
};

/** A period's first and last days, both counted: `{ from: '2025-10-08', to: '2026-10-07' }`. */
export interface Period {
  from: string;
  to: string;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function iso(year: number, month: number, day: number): string {
  return [String(year).padStart(4, '0'), month, day]
    .map((part) => String(part).padStart(2, '0'))
    .join('-');
}

function parts(day: string): [number, number, number] {
  const [year, month, date] = day.split('-').map(Number);
  return [year, month, date];
}

function daysInMonth(year: number, month: number): number {
  if (month === 2) return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function isIsoDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const [year, month, day] = parts(value);
  return month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month);
}

/** Today in UTC, the day the API counts from: `2026-10-07`. */
export function todayUtc(now: Date = new Date()): string {
  return iso(now.getUTCFullYear(), now.getUTCMonth() + 1, now.getUTCDate());
}

/** The same day `months` months before, or that month's last day where the day does not exist:
 * 31 October six months back is 30 April (SPEC F5). */
export function monthsBefore(day: string, months: number): string {
  const [year, month, date] = parts(day);
  const index = year * 12 + month - 1 - months;
  const back = { year: Math.floor(index / 12), month: (index % 12) + 1 };
  return iso(back.year, back.month, Math.min(date, daysInMonth(back.year, back.month)));
}

/** The first day of the `months` months ending on `last`: the day after the same day that many
 * months before, or after that month's last day where the day does not exist. 12 months ending
 * 8 October 2026 start on 9 October 2025, and 6 ending 31 October start on 1 May (D69). */
export function periodStart(last: string, months: number): string {
  const [year, month, day] = parts(monthsBefore(last, months));
  if (day < daysInMonth(year, month)) return iso(year, month, day + 1);
  return month < 12 ? iso(year, month + 1, 1) : iso(year + 1, 1, 1);
}

/** The 1 April that opened the financial year `day` falls in. */
export function fyStart(day: string): string {
  const [year, month, date] = parts(day);
  const opened = month > FY_START.month || (month === FY_START.month && date >= FY_START.day);
  return iso(opened ? year : year - 1, FY_START.month, FY_START.day);
}

/** A preset's dates against `today` (SPEC F5, D64). */
export function presetPeriod(name: PresetName, today: string): Period {
  switch (name) {
    case 'last_3_months':
      return { from: periodStart(today, 3), to: today };
    case 'last_6_months':
      return { from: periodStart(today, 6), to: today };
    case 'last_12_months':
      return { from: periodStart(today, 12), to: today };
    case 'fy_to_date':
      return { from: fyStart(today), to: today };
    case 'last_fy': {
      const lastDay = dayBefore(fyStart(today));
      return { from: fyStart(lastDay), to: lastDay };
    }
  }
}

/** Why the API would refuse a custom period, in the words the bar shows under its dates, or null
 * when it would take it (SPEC section 8, D64). */
export function periodProblem({ from, to }: Period): string | null {
  if (!isIsoDate(from)) return 'Enter a date in From.';
  if (!isIsoDate(to)) return 'Enter a date in To.';
  if (from < REPORTING_START) return `From must be on or after ${formatDate(REPORTING_START)}.`;
  if (to > PERIOD_LAST) return `To must be on or before ${formatDate(PERIOD_LAST)}.`;
  if (from > to) return 'From must be on or before To.';
  return null;
}

/** A custom period from the URL, or null when the API would refuse it. */
export function customPeriod(from: string | null, to: string | null): Period | null {
  if (from === null || to === null) return null;
  return periodProblem({ from, to }) === null ? { from, to } : null;
}
