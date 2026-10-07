// Values shared across the app. Anything the API fixes (SPEC section 8) is mirrored here once.

export const API_PREFIX = '/api/v1';
export const REFRESH_STORAGE_KEY = 'acme.refresh';

export const PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_PAGE_SIZE = 25;

export const REPORTING_CURRENCIES = ['usd', 'eur', 'local'] as const;
export type ReportingCurrency = (typeof REPORTING_CURRENCIES)[number];

export const EMPLOYEE_STATUSES = ['active', 'exited', 'upcoming'] as const;
export type EmployeeStatus = (typeof EMPLOYEE_STATUSES)[number];

/** `apiUrl('/auth/me/')` is the absolute URL for the API path on the page's own origin. */
export function apiUrl(path: string): string {
  const base = typeof window !== 'undefined' ? window.location.href : 'http://localhost/';
  return new URL(`${API_PREFIX}${path}`, base).toString();
}
