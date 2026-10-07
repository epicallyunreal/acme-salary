import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime, parseIsoDate } from './dates';

describe('formatDate', () => {
  it('writes day, short month and year', () => {
    expect(formatDate('2026-10-07')).toBe('7 Oct 2026');
    expect(formatDate('2026-01-01')).toBe('1 Jan 2026');
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
  it("adds the time in the viewer's zone", () => {
    expect(formatDateTime('2026-10-07T12:00:00Z')).toMatch(/^7 Oct 2026, \d\d:\d\d$/);
    expect(formatDateTime(null)).toBe('');
  });
});
