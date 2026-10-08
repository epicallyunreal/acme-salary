import { describe, expect, it } from 'vitest';

import { formatCompact, formatMoney, monthly } from './money';

const nbsp = '\u00a0';

describe('formatMoney', () => {
  it('writes the code before the figure and drops the cents by default', () => {
    expect(formatMoney('1450000.00', 'INR')).toBe(`INR${nbsp}1,450,000`);
    expect(formatMoney('17400.00', 'USD')).toBe(`USD${nbsp}17,400`);
  });

  it('keeps two decimals when asked', () => {
    expect(formatMoney('17400.00', 'USD', { fraction: 2 })).toBe(`USD${nbsp}17,400.00`);
    expect(formatMoney('0.50', 'EUR', { fraction: 2 })).toBe(`EUR${nbsp}0.50`);
  });

  it('never goes through a float', () => {
    expect(formatMoney('9007199254740993.00', 'USD')).toBe(`USD${nbsp}9,007,199,254,740,993`);
  });

  it('writes a change with its sign, and none for no change', () => {
    expect(formatMoney('23000.00', 'USD', { signed: true })).toBe(`+USD${nbsp}23,000`);
    expect(formatMoney('-6250.06', 'USD', { signed: true })).toBe(`-USD${nbsp}6,250`);
    expect(formatMoney('0.00', 'USD', { signed: true })).toBe(`USD${nbsp}0`);
  });

  it('rounds half up when the figure has more decimals than shown', () => {
    expect(formatMoney('12345.50', 'GBP')).toBe(`GBP${nbsp}12,346`);
  });
});

describe('formatCompact', () => {
  it('abbreviates for axes and cards', () => {
    expect(formatCompact('1200000', 'USD')).toBe(`USD${nbsp}1.2M`);
    expect(formatCompact('96000', 'EUR')).toBe(`EUR${nbsp}96K`);
  });
});

describe('monthly', () => {
  it('divides the annual figure by twelve to the cent, half up, without a float', () => {
    expect(monthly('120000.00')).toBe('10000.00');
    expect(monthly('100000.00')).toBe('8333.33');
    expect(monthly('100.05')).toBe('8.34');
    expect(monthly('1')).toBe('0.08');
    expect(monthly('100001.95')).toBe('8333.50');
    expect(monthly('9007199254740993.00')).toBe('750599937895082.75');
    expect(formatMoney(monthly('120000.00'), 'USD')).toBe(`USD${nbsp}10,000`);
  });
});
