import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type { EmployeeRow, ListParams, Page } from './types';

export function listEmployees(params: ListParams): Promise<Page<EmployeeRow>> {
  return apiFetch<Page<EmployeeRow>>('/employees/', { query: { ...params } });
}

/** The directory page. Keeps the previous rows on screen while the next page or filter loads. */
export function useEmployeeList(params: ListParams) {
  return useQuery({
    queryKey: keys.employees.list(params),
    queryFn: () => listEmployees(params),
    placeholderData: keepPreviousData,
  });
}
