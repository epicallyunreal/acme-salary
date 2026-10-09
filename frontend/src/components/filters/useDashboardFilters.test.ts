import { act, renderHook } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { DASHBOARD_DEFAULTS, useDashboardFilters } from './useDashboardFilters';

function wrapperAt(url: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(MemoryRouter, { initialEntries: [url] }, children);
  };
}

describe('useDashboardFilters', () => {
  it('a set or a card control captured before a reset and called after it brings nothing back (D76)', () => {
    const { result } = renderHook(() => useDashboardFilters(), {
      wrapper: wrapperAt('/?country=IN&period=last_fy&trend.measure=headcount'),
    });
    const { set, setControl } = result.current;

    act(() => result.current.reset());
    act(() => set({ include_exited: true }));
    act(() => setControl('gap', 'bonus'));

    expect(result.current.filters).toMatchObject({
      country: [],
      include_exited: true,
      period: DASHBOARD_DEFAULTS.period,
    });
    expect(result.current.controls).toMatchObject({ trend: 'total_cost', gap: 'bonus' });
  });
});
