import { describe, expect, it } from 'vitest';

import {
  DEFAULT_STATE,
  fromSearchParams,
  type GridState,
  fromSortModel,
  isFiltered,
  toListParams,
  toPaginationModel,
  toSearchParams,
  toSortModel,
} from './serverModel';

describe('toListParams', () => {
  it('maps the zero-based grid page onto DRF one-based pages and leaves empties out', () => {
    const params = toListParams({
      paginationModel: { page: 2, pageSize: 50 },
      sortModel: [],
      filters: DEFAULT_STATE,
      search: '',
    });

    expect(params).toEqual({ page: 3, page_size: 50 });
  });

  it('prefixes a descending sort and maps the column onto the API alias', () => {
    const params = toListParams({
      paginationModel: { page: 0, pageSize: 25 },
      sortModel: [{ field: 'gross_reporting', sort: 'desc' }],
      filters: { ...DEFAULT_STATE, country: ['IN', 'US'], level: [3], currency: 'eur' },
      search: 'asha',
    });

    expect(params).toEqual({
      page: 1,
      page_size: 25,
      ordering: '-gross',
      search: 'asha',
      country: ['IN', 'US'],
      level: [3],
      currency: 'eur',
    });
  });

  it('ignores a sort on a column the API cannot order by', () => {
    expect(fromSortModel([{ field: 'status', sort: 'asc' }])).toBe('');
    expect(fromSortModel([{ field: 'full_name', sort: 'asc' }])).toBe('full_name');
    expect(fromSortModel([])).toBe('');
  });
});

describe('URL round trip', () => {
  it('drops defaults so a plain directory link has no query', () => {
    expect(toSearchParams(DEFAULT_STATE).toString()).toBe('');
  });

  it('writes every set value and reads it back unchanged', () => {
    const state = {
      ...DEFAULT_STATE,
      search: 'rao',
      country: ['IN'],
      department: ['engineering', 'sales'],
      designation: ['Senior Engineer'],
      level: [3, 5],
      status: 'active' as const,
      gross_min: '10000',
      gross_max: '250000.50',
      joined_after: '2020-01-01',
      joined_before: '2026-09-30',
      currency: 'local' as const,
      page: 3,
      page_size: 100,
      ordering: '-gross',
    };

    const params = toSearchParams(state);

    expect(params.get('country')).toBe('IN');
    expect(params.get('department')).toBe('engineering,sales');
    expect(params.get('page')).toBe('3');
    expect(fromSearchParams(params)).toEqual(state);
  });

  it('falls back to defaults for malformed values instead of sending them to the API', () => {
    const params = new URLSearchParams(
      'page=abc&page_size=7&status=gone&currency=gbp&level=1,x,9&ordering=salary&gross_min=1e5&joined_after=yesterday',
    );

    const state = fromSearchParams(params);

    expect(state.page).toBe(1);
    expect(state.page_size).toBe(25);
    expect(state.status).toBe('');
    expect(state.currency).toBe('usd');
    expect(state.level).toEqual([1]);
    expect(state.ordering).toBe('');
    expect(state.gross_min).toBe('');
    expect(state.joined_after).toBe('');
  });

  it('derives the grid models from the URL state', () => {
    const state = { ...DEFAULT_STATE, page: 2, page_size: 50, ordering: '-gross' };

    expect(toPaginationModel(state)).toEqual({ page: 1, pageSize: 50 });
    expect(toSortModel(state)).toEqual([{ field: 'gross_reporting', sort: 'desc' }]);
    expect(toSortModel({ ...state, ordering: 'full_name' })).toEqual([
      { field: 'full_name', sort: 'asc' },
    ]);
    expect(toSortModel(DEFAULT_STATE)).toEqual([]);
  });
});

describe('isFiltered', () => {
  it('counts filters and the search, not the currency or the paging', () => {
    expect(isFiltered(DEFAULT_STATE)).toBe(false);
    const paged: GridState = { ...DEFAULT_STATE, currency: 'eur', page: 4 };
    expect(isFiltered(paged)).toBe(false);
    expect(isFiltered({ ...DEFAULT_STATE, search: 'x' })).toBe(true);
    expect(isFiltered({ ...DEFAULT_STATE, level: [2] })).toBe(true);
  });
});
