import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, formatMonthShort, parseIsoDate } from './dates';

describe('formatDate', () => {
  it('writes day, short month and year', () => {
    expect(formatDate('2026-10-07')).toBe('7 Oct 2026');
    expect(formatDate('2026-01-01')).toBe('1 Jan 2026');
  });

  it('writes every month in three letters, September as Sep (D62)', () => {
    expect(formatDate('2026-09-30')).toBe('30 Sep 2026');
  });

  it('leaves null and empty values blank', () => {
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
    expect(formatDate('')).toBe('');
  });

  it('builds the date from its parts so the time zone cannot shift it', () => {
    const parsed = parseIsoDate('2026-01-01');
    expect([parsed.getFullYear(), parsed.getMonth(), parsed.getDate()]).toEqual([2026, 0, 1]);
  });
});

describe('formatDateTime', () => {
  it("adds the time in the viewer's zone (the tests run in New York)", () => {
    expect(formatDateTime('2026-10-07T12:00:00Z')).toBe('7 Oct 2026, 08:00');
    expect(formatDateTime('2026-10-08T03:30:00Z')).toBe('7 Oct 2026, 23:30');
    expect(formatDateTime(null)).toBe('');
  });

  it('writes September as Sep', () => {
    expect(formatDateTime('2026-09-30T16:05:00Z')).toBe('30 Sep 2026, 12:05');
  });
});

describe('formatMonthShort', () => {
  it('writes a month on an axis with a two-digit year', () => {
    expect(formatMonthShort('2026-09-30')).toBe('Sep 26');
    expect(formatMonthShort('2024-10-31')).toBe('Oct 24');
  });
});
