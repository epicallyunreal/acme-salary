import {
  keepPreviousData,
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type { EmployeeDetail, EmployeeRow, ExitInput, ListParams, Page } from './types';

export function listEmployees(
  params: ListParams,
  signal?: AbortSignal,
): Promise<Page<EmployeeRow>> {
  return apiFetch<Page<EmployeeRow>>('/employees/', { query: { ...params }, signal });
}

/** The directory page. Keeps the previous rows on screen while the next page or filter loads. */
export function useEmployeeList(params: ListParams) {
  return useQuery({
    queryKey: keys.employees.list(params),
    queryFn: ({ signal }) => listEmployees(params, signal),
    placeholderData: keepPreviousData,
  });
}

export function getEmployee(id: number, signal?: AbortSignal): Promise<EmployeeDetail> {
  return apiFetch<EmployeeDetail>(`/employees/${id}/`, { signal });
}

export function useEmployee(id: number) {
  return useQuery({
    queryKey: keys.employees.detail(id),
    queryFn: ({ signal }) => getEmployee(id, signal),
  });
}

/** After a write to one employee: their detail, history and audit list, the directory and the
 * insights all refetch (DESIGN section 6). */
export function invalidateEmployee(client: QueryClient, id: number) {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.employees.detail(id) }),
    client.invalidateQueries({ queryKey: [...keys.employees.all, 'list'] }),
    client.invalidateQueries({ queryKey: keys.insights.all }),
  ]);
}

export function useExitEmployee(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: ExitInput) =>
      apiFetch<EmployeeDetail>(`/employees/${id}/exit/`, { method: 'POST', body: input }),
    onSuccess: () => invalidateEmployee(client, id),
  });
}
