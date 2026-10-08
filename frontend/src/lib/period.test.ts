import { describe, expect, it } from 'vitest';

import { customPeriod, monthsBefore, periodProblem, presetPeriod, todayUtc } from './period';

describe('todayUtc', () => {
  it("is today in UTC, not in the viewer's zone (the tests run in New York)", () => {
    // 23:30 on 7 October in New York is already 8 October in UTC.
    expect(todayUtc(new Date('2026-10-08T03:30:00Z'))).toBe('2026-10-08');
    expect(todayUtc(new Date('2026-10-07T12:00:00Z'))).toBe('2026-10-07');
  });
});

describe('presetPeriod', () => {
  it('counts Last N months back to the same day, ending today', () => {
    expect(presetPeriod('last_3_months', '2026-10-07')).toEqual({
      from: '2026-07-07',
      to: '2026-10-07',
    });
    expect(presetPeriod('last_6_months', '2026-10-07')).toEqual({
      from: '2026-04-07',
      to: '2026-10-07',
    });
    expect(presetPeriod('last_12_months', '2026-10-07')).toEqual({
      from: '2025-10-07',
      to: '2026-10-07',
    });
  });

  it("takes the month's last day where the day does not exist (SPEC F5)", () => {
    expect(presetPeriod('last_6_months', '2026-10-31').from).toBe('2026-04-30');
    expect(presetPeriod('last_12_months', '2026-02-28').from).toBe('2025-02-28');
    expect(presetPeriod('last_12_months', '2028-02-29').from).toBe('2027-02-28');
  });

  it('ends Last 3 months on 31 May at the end of February, in a leap year and in another', () => {
    expect(monthsBefore('2028-05-31', 3)).toBe('2028-02-29');
    expect(monthsBefore('2026-05-31', 3)).toBe('2026-02-28');
    expect(monthsBefore('2100-05-31', 3)).toBe('2100-02-28');
    expect(monthsBefore('2000-05-31', 3)).toBe('2000-02-29');
  });

  it('a month back from 31 March is the end of February', () => {
    expect(monthsBefore('2028-03-31', 1)).toBe('2028-02-29');
    expect(monthsBefore('2026-03-31', 1)).toBe('2026-02-28');
    expect(monthsBefore('2026-01-15', 1)).toBe('2025-12-15');
  });

  it('opens the financial year on 1 April, so 31 March is still the year before', () => {
    expect(presetPeriod('fy_to_date', '2026-03-31')).toEqual({
      from: '2025-04-01',
      to: '2026-03-31',
    });
    expect(presetPeriod('fy_to_date', '2026-04-01')).toEqual({
      from: '2026-04-01',
      to: '2026-04-01',
    });
    expect(presetPeriod('fy_to_date', '2026-10-07')).toEqual({
      from: '2026-04-01',
      to: '2026-10-07',
    });
  });

  it('gives Last FY as the 1 April to 31 March before the current one', () => {
    expect(presetPeriod('last_fy', '2026-10-07')).toEqual({
      from: '2025-04-01',
      to: '2026-03-31',
    });
    expect(presetPeriod('last_fy', '2026-03-31')).toEqual({
      from: '2024-04-01',
      to: '2025-03-31',
    });
    expect(presetPeriod('last_fy', '2026-04-01')).toEqual({
      from: '2025-04-01',
      to: '2026-03-31',
    });
  });
});

describe('periodProblem', () => {
  it('takes any range from 1 January 2015 to 31 December 2100, one day included', () => {
    expect(periodProblem({ from: '2015-01-01', to: '2100-12-31' })).toBeNull();
    expect(periodProblem({ from: '2026-10-07', to: '2026-10-07' })).toBeNull();
  });

  it('refuses what the API would refuse, in the words the bar shows', () => {
    expect(periodProblem({ from: '2014-12-31', to: '2026-10-07' })).toBe(
      'From must be on or after 1 Jan 2015.',
    );
    expect(periodProblem({ from: '2026-10-07', to: '2101-01-01' })).toBe(
      'To must be on or before 31 Dec 2100.',
    );
    expect(periodProblem({ from: '2026-10-08', to: '2026-10-07' })).toBe(
      'From must be on or before To.',
    );
    expect(periodProblem({ from: '', to: '2026-10-07' })).toBe('Enter a date in From.');
    expect(periodProblem({ from: '2026-10-07', to: '2026-02-30' })).toBe('Enter a date in To.');
  });
});

describe('customPeriod', () => {
  it('reads a range the API takes, and nothing else, from the URL', () => {
    expect(customPeriod('2026-01-01', '2026-03-31')).toEqual({
      from: '2026-01-01',
      to: '2026-03-31',
    });
    expect(customPeriod('2026-03-31', '2026-01-01')).toBeNull();
    expect(customPeriod('2026-01-01', null)).toBeNull();
    expect(customPeriod('01/01/2026', '2026-03-31')).toBeNull();
  });
});
