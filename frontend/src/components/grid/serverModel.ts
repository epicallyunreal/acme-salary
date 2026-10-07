// The adapter between the URL, the DataGrid's models and the API's parameters (DESIGN section 6).
// Pure functions: the URL is the one source of truth and everything else is derived from it.

import type { GridPaginationModel, GridSortModel } from '@mui/x-data-grid';

import type { EmployeeStatus, ListParams, ReportingCurrency } from '../../api/types';
import {
  DEFAULT_PAGE_SIZE,
  EMPLOYEE_STATUSES,
  LEVELS,
  PAGE_SIZES,
  REPORTING_CURRENCIES,
} from '../../lib/constants';

export interface DirectoryFilters {
  search: string;
  country: string[];
  department: string[];
  designation: string[];
  level: number[];
  status: EmployeeStatus | '';
  gross_min: string;
  gross_max: string;
  joined_after: string;
  joined_before: string;
  currency: ReportingCurrency;
}

/** Everything the directory keeps in the URL: the filters plus page, page size and ordering. */
export interface GridState extends DirectoryFilters {
  page: number;
  page_size: number;
  ordering: string;
}

export const FILTER_KEYS = [
  'search',
  'country',
  'department',
  'designation',
  'level',
  'status',
  'gross_min',
  'gross_max',
  'joined_after',
  'joined_before',
  'currency',
] as const satisfies readonly (keyof DirectoryFilters)[];

export const DEFAULT_STATE: GridState = {
  search: '',
  country: [],
  department: [],
  designation: [],
  level: [],
  status: '',
  gross_min: '',
  gross_max: '',
  joined_after: '',
  joined_before: '',
  currency: 'usd',
  page: 1,
  page_size: DEFAULT_PAGE_SIZE,
  ordering: '',
};

/** Grid column field to the API's ordering alias. Columns missing here are not sortable. */
export const SORT_FIELDS: Record<string, string> = {
  employee_code: 'employee_code',
  full_name: 'full_name',
  department: 'department',
  country: 'country',
  designation: 'designation',
  level: 'level',
  gross_reporting: 'gross',
  joining_date: 'joining_date',
};

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^\d+(\.\d{1,2})?$/;

export function csv(value: string | null): string[] {
  return value
    ? value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    : [];
}

export function oneOf<T extends string>(
  value: string | null,
  allowed: readonly T[],
  fallback: T,
): T {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

function matching(value: string | null, pattern: RegExp): string {
  return value !== null && pattern.test(value) ? value : '';
}

/** `local` is a reporting currency only while exactly one country is selected (DESIGN 6). */
export function withCurrencyRule<T extends { currency: ReportingCurrency; country: string[] }>(
  state: T,
): T {
  if (state.currency === 'local' && state.country.length !== 1)
    return { ...state, currency: 'usd' };
  return state;
}

/** Reads the URL. Anything malformed falls back to the default rather than reaching the API. */
export function fromSearchParams(params: URLSearchParams): GridState {
  const page = Number(params.get('page'));
  const pageSize = Number(params.get('page_size'));
  const ordering = params.get('ordering') ?? '';
  const orderingField = ordering.replace(/^-/, '');
  return withCurrencyRule({
    search: params.get('search') ?? '',
    country: csv(params.get('country')),
    department: csv(params.get('department')),
    designation: csv(params.get('designation')),
    level: csv(params.get('level'))
      .map(Number)
      .filter((level): level is (typeof LEVELS)[number] =>
        (LEVELS as readonly number[]).includes(level),
      ),
    status: oneOf(params.get('status'), EMPLOYEE_STATUSES, '' as const),
    gross_min: matching(params.get('gross_min'), AMOUNT),
    gross_max: matching(params.get('gross_max'), AMOUNT),
    joined_after: matching(params.get('joined_after'), ISO_DATE),
    joined_before: matching(params.get('joined_before'), ISO_DATE),
    currency: oneOf(params.get('currency'), REPORTING_CURRENCIES, 'usd'),
    page: Number.isInteger(page) && page > 0 ? page : 1,
    page_size: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
    ordering: Object.values(SORT_FIELDS).includes(orderingField) ? ordering : '',
  });
}

/** Writes the URL. Defaults and empties are dropped so links stay short. */
export function toSearchParams(state: GridState): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of Object.keys(DEFAULT_STATE) as (keyof GridState)[]) {
    const value = state[key];
    const fallback = DEFAULT_STATE[key];
    if (Array.isArray(value)) {
      if (value.length) params.set(key, value.join(','));
    } else if (value !== fallback && value !== '') {
      params.set(key, String(value));
    }
  }
  return params;
}

/** The URL's one-based page as the grid's zero-based model. */
export function toPaginationModel(page: number, pageSize: number): GridPaginationModel {
  return { page: page - 1, pageSize };
}

/** `-gross` becomes a descending sort on the reporting-gross column. */
export function toSortModel(ordering: string): GridSortModel {
  if (!ordering) return [];
  const desc = ordering.startsWith('-');
  const alias = desc ? ordering.slice(1) : ordering;
  const field = Object.keys(SORT_FIELDS).find((column) => SORT_FIELDS[column] === alias);
  return field ? [{ field, sort: desc ? 'desc' : 'asc' }] : [];
}

export function fromSortModel(model: GridSortModel): string {
  const first = model[0];
  if (!first || !first.sort) return '';
  const alias = SORT_FIELDS[first.field];
  if (!alias) return '';
  return `${first.sort === 'desc' ? '-' : ''}${alias}`;
}

interface ListInput {
  paginationModel: GridPaginationModel;
  sortModel: GridSortModel;
  filters: DirectoryFilters;
  search: string;
}

/** The DataGrid's zero-based page becomes DRF's one-based page; empties are left out. */
export function toListParams({
  paginationModel,
  sortModel,
  filters,
  search,
}: ListInput): ListParams {
  const ordering = fromSortModel(sortModel);
  return {
    page: paginationModel.page + 1,
    page_size: paginationModel.pageSize,
    ordering: ordering || undefined,
    search: search || undefined,
    country: filters.country.length ? filters.country : undefined,
    department: filters.department.length ? filters.department : undefined,
    designation: filters.designation.length ? filters.designation : undefined,
    level: filters.level.length ? filters.level : undefined,
    status: filters.status || undefined,
    gross_min: filters.gross_min || undefined,
    gross_max: filters.gross_max || undefined,
    joined_after: filters.joined_after || undefined,
    joined_before: filters.joined_before || undefined,
    currency: filters.currency === 'usd' ? undefined : filters.currency,
  };
}

/** True when any filter or the search is set, so the empty state can say "clear a filter". */
export function isFiltered(state: DirectoryFilters): boolean {
  return FILTER_KEYS.some((key) => {
    if (key === 'currency') return false;
    const value = state[key];
    return Array.isArray(value) ? value.length > 0 : value !== '';
  });
}
