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

  it('sends every filter under its SPEC F4 name', () => {
    const params = toListParams({
      paginationModel: { page: 0, pageSize: 25 },
      sortModel: [],
      filters: {
        ...DEFAULT_STATE,
        country: ['IN'],
        department: ['engineering'],
        designation: ['Senior Engineer'],
        level: [3],
        status: 'exited',
        gross_min: '10000',
        gross_max: '250000.50',
        joined_after: '2020-01-01',
        joined_before: '2026-09-30',
        currency: 'local',
      },
      search: '',
    });

    expect(params).toEqual({
      page: 1,
      page_size: 25,
      country: ['IN'],
      department: ['engineering'],
      designation: ['Senior Engineer'],
      level: [3],
      status: 'exited',
      gross_min: '10000',
      gross_max: '250000.50',
      joined_after: '2020-01-01',
      joined_before: '2026-09-30',
      currency: 'local',
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
    expect(state.ordering).toBe('employee_code');
    expect(state.gross_min).toBe('');
    expect(state.joined_after).toBe('');
  });

  it('drops local when the URL does not carry exactly one country', () => {
    expect(fromSearchParams(new URLSearchParams('currency=local')).currency).toBe('usd');
    expect(fromSearchParams(new URLSearchParams('currency=local&country=IN,US')).currency).toBe(
      'usd',
    );
    expect(fromSearchParams(new URLSearchParams('currency=local&country=IN')).currency).toBe(
      'local',
    );
  });

  it('ignores a reporting date in the URL, which the UI never sends (P1)', () => {
    const state = fromSearchParams(new URLSearchParams('on=2026-01-01&page=2'));
    const params = toListParams({
      paginationModel: toPaginationModel(state.page, state.page_size),
      sortModel: [],
      filters: state,
      search: '',
    });

    expect(toSearchParams(state).toString()).toBe('page=2');
    expect('on' in params).toBe(false);
  });

  it('derives the grid models from the URL state', () => {
    const state = { ...DEFAULT_STATE, page: 2, page_size: 50, ordering: '-gross' };

    expect(toPaginationModel(state.page, state.page_size)).toEqual({ page: 1, pageSize: 50 });
    expect(toSortModel(state.ordering)).toEqual([{ field: 'gross_reporting', sort: 'desc' }]);
    expect(toSortModel('full_name')).toEqual([{ field: 'full_name', sort: 'asc' }]);
    expect(toSortModel('')).toEqual([]);
  });

  it('sorts by Code ascending by default and leaves that out of the URL and the request', () => {
    const state = fromSearchParams(new URLSearchParams());
    const list = (ordering: string) =>
      toListParams({
        paginationModel: toPaginationModel(1, 25),
        sortModel: toSortModel(ordering),
        filters: state,
        search: '',
      }).ordering;

    expect(toSortModel(state.ordering)).toEqual([{ field: 'employee_code', sort: 'asc' }]);
    expect(toSearchParams(state).toString()).toBe('');
    expect(list(state.ordering)).toBeUndefined();
    expect(list('-employee_code')).toBe('-employee_code');
    expect(toSearchParams({ ...state, ordering: '-employee_code' }).toString()).toBe(
      'ordering=-employee_code',
    );
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
