import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from './client';
import { invalidateEmployee } from './employees';
import { keys } from './keys';
import type { CompensationRecord, HistoryParams } from './types';

export function listHistory(
  employeeId: number,
  params: HistoryParams,
  signal?: AbortSignal,
): Promise<CompensationRecord[]> {
  return apiFetch<CompensationRecord[]>(`/employees/${employeeId}/compensation/`, {
    query: { ...params },
    signal,
  });
}

/** Every record of one employee, newest first, cancelled ones included. */
export function useCompensationHistory(employeeId: number, params: HistoryParams = {}) {
  return useQuery({
    queryKey: keys.employees.history(employeeId, params),
    queryFn: ({ signal }) => listHistory(employeeId, params, signal),
  });
}

/** DELETE marks a scheduled revision cancelled; the row stays in history (D20). */
export function useCancelRevision(employeeId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (recordId: number) =>
      apiFetch<CompensationRecord>(`/compensation/${recordId}/`, { method: 'DELETE' }),
    onSuccess: () => invalidateEmployee(client, employeeId),
  });
}
