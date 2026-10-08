// Values shared across the app. Anything the API fixes (SPEC section 8) is mirrored here once.

import type { Gender } from '../api/types';

export const API_PREFIX = '/api/v1';
export const REFRESH_STORAGE_KEY = 'acme.refresh';

export const PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

export const REPORTING_CURRENCIES = ['usd', 'eur', 'local'] as const;
export const EMPLOYEE_STATUSES = ['active', 'exited', 'upcoming'] as const;
/** The directory's Status filter: Active by default, and Any for everyone (D64). */
export const DIRECTORY_STATUSES = [...EMPLOYEE_STATUSES, 'any'] as const;
export const LEVELS = [1, 2, 3, 4, 5, 6] as const;

/** ACME's financial year runs from 1 April to 31 March (SPEC F5). The one place it is defined. */
export const FY_START = { month: 4, day: 1 } as const;
/** The reporting cut-off, 1 April 2020, the start of FY 2020-21: the first day a period may
 * cover, as the API bounds `from` and `to` (D70). Pay history before it stays. */
export const REPORTING_START = '2020-04-01';
/** The last day a period may cover (D64). */
export const PERIOD_LAST = '2100-12-31';

/** The genders the API accepts, in the order the forms offer them (SPEC section 5). */
export const GENDERS = [
  'female',
  'male',
  'other',
  'undisclosed',
] as const satisfies readonly Gender[];
export const GENDER_LABELS: Record<Gender, string> = {
  female: 'Female',
  male: 'Male',
  other: 'Other',
  undisclosed: 'Undisclosed',
};

/** `apiUrl('/auth/me/')` is the absolute URL for the API path on the page's own origin. */
export function apiUrl(path: string): string {
  const base = typeof window !== 'undefined' ? window.location.href : 'http://localhost/';
  return new URL(`${API_PREFIX}${path}`, base).toString();
}
