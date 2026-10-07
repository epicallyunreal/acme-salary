import {
  keepPreviousData,
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type {
  EmployeeCreateInput,
  EmployeeDetail,
  EmployeeRow,
  ExitInput,
  IdentityPatch,
  ListParams,
  Page,
  WithWarnings,
} from './types';

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

/** Create answers with the new employee's detail and the validators' warnings (D27). */
export function useCreateEmployee() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: EmployeeCreateInput) =>
      apiFetch<WithWarnings<EmployeeDetail>>('/employees/', { method: 'POST', body: input }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: [...keys.employees.all, 'list'] }),
        client.invalidateQueries({ queryKey: keys.insights.all }),
      ]),
  });
}

export function useUpdateEmployee(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: IdentityPatch) =>
      apiFetch<EmployeeDetail>(`/employees/${id}/`, { method: 'PATCH', body: patch }),
    onSuccess: () => invalidateEmployee(client, id),
  });
}
