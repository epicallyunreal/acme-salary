import { useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys } from './keys';
import type { AuditEntry, Page } from './types';

/** The audit tab asks for one page of 100 and says so when there are more (D42). */
export const AUDIT_PAGE_SIZE = 100;

export function listAudit(employeeId: number, signal?: AbortSignal): Promise<Page<AuditEntry>> {
  return apiFetch<Page<AuditEntry>>(`/employees/${employeeId}/audit/`, {
    query: { page_size: AUDIT_PAGE_SIZE },
    signal,
  });
}

export function useAudit(employeeId: number) {
  return useQuery({
    queryKey: keys.employees.audit(employeeId),
    queryFn: ({ signal }) => listAudit(employeeId, signal),
  });
}
