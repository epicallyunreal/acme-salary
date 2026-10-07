import { act, renderHook } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { DEFAULT_STATE } from '../grid/serverModel';
import { applyChange, useUrlFilters } from './useUrlFilters';

function wrapperAt(url: string) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(MemoryRouter, { initialEntries: [url] }, children);
  };
}

describe('applyChange', () => {
  it('sends a filter change back to page 1 but leaves the page alone for sort and size', () => {
    const paged = { ...DEFAULT_STATE, page: 4 };

    expect(applyChange(paged, { country: ['IN'] }).page).toBe(1);
    expect(applyChange(paged, { search: 'x' }).page).toBe(1);
    expect(applyChange(paged, { ordering: '-gross' }).page).toBe(4);
    expect(applyChange(paged, { page_size: 50 }).page).toBe(4);
    expect(applyChange(paged, { page: 2 }).page).toBe(2);
  });

  it('keeps local only while exactly one country is selected', () => {
    const local = { ...DEFAULT_STATE, country: ['IN'], currency: 'local' as const };

    expect(applyChange(local, { country: ['IN', 'US'] }).currency).toBe('usd');
    expect(applyChange(local, { country: [] }).currency).toBe('usd');
    expect(applyChange(local, { country: ['US'] }).currency).toBe('local');
    expect(applyChange(DEFAULT_STATE, { currency: 'local' }).currency).toBe('usd');
    expect(applyChange({ ...DEFAULT_STATE, country: ['IN'] }, { currency: 'local' }).currency).toBe(
      'local',
    );
  });
});

describe('useUrlFilters', () => {
  it('reads the URL and writes changes back to it', () => {
    const { result } = renderHook(() => useUrlFilters(), {
      wrapper: wrapperAt('/employees?country=IN&page=3&ordering=-gross'),
    });

    expect(result.current.state.country).toEqual(['IN']);
    expect(result.current.state.page).toBe(3);
    expect(result.current.state.ordering).toBe('-gross');

    act(() => result.current.set({ department: ['sales'] }));

    expect(result.current.state.department).toEqual(['sales']);
    expect(result.current.state.page).toBe(1);
    expect(result.current.state.ordering).toBe('-gross');
  });

  it('resets every filter but keeps the page size', () => {
    const { result } = renderHook(() => useUrlFilters(), {
      wrapper: wrapperAt('/employees?country=IN&search=rao&page_size=100&page=2'),
    });

    act(() => result.current.reset());

    expect(result.current.state).toEqual({ ...DEFAULT_STATE, page_size: 100 });
  });
});
