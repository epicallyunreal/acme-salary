import {
  keepPreviousData,
  type QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import { saveFile } from '../lib/download';
import { apiDownload, apiFetch } from './client';
import { keys } from './keys';
import type { ImportBatch, ImportRow, ImportRowParams, Page } from './types';

/** The batch list, newest first, one page of 25 at a time (SPEC section 8). */
export function listImports(page: number, signal?: AbortSignal): Promise<Page<ImportBatch>> {
  return apiFetch<Page<ImportBatch>>('/imports/', { query: { page }, signal });
}

export function useImportList(page: number) {
  return useQuery({
    queryKey: keys.imports.list(page),
    queryFn: ({ signal }) => listImports(page, signal),
    placeholderData: keepPreviousData,
  });
}

export function uploadImport(file: File): Promise<ImportBatch> {
  const body = new FormData();
  body.append('file', file);
  return apiFetch<ImportBatch>('/imports/', { method: 'POST', body });
}

/** Stage a file. The new batch is put in the cache, so its review page opens without a wait. */
export function useUploadImport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: uploadImport,
    onSuccess: (batch) => {
      client.setQueryData(keys.imports.detail(batch.id), batch);
      return client.invalidateQueries({ queryKey: keys.imports.lists });
    },
  });
}

/** The XLSX template for one country, or for all of them when `country` is omitted. */
export async function downloadTemplate(country?: string) {
  const { blob, fileName } = await apiDownload('/imports/template/', { query: { country } });
  saveFile(blob, fileName ?? `acme-import-template${country ? `-${country}` : ''}.xlsx`);
}

export function getImport(id: number, signal?: AbortSignal): Promise<ImportBatch> {
  return apiFetch<ImportBatch>(`/imports/${id}/`, { signal });
}

export function useImportBatch(id: number) {
  return useQuery({
    queryKey: keys.imports.detail(id),
    queryFn: ({ signal }) => getImport(id, signal),
  });
}

export function listImportRows(
  id: number,
  params: ImportRowParams,
  signal?: AbortSignal,
): Promise<Page<ImportRow>> {
  return apiFetch<Page<ImportRow>>(`/imports/${id}/rows/`, { query: { ...params }, signal });
}

/** The review grid. Keeps the previous rows on screen while the next page or filter loads. */
export function useImportRows(id: number, params: ImportRowParams) {
  return useQuery({
    queryKey: keys.imports.rows(id, params),
    queryFn: ({ signal }) => listImportRows(id, params, signal),
    placeholderData: keepPreviousData,
  });
}

/** The batch and its rows share a key prefix, so this refreshes the summary and the grid. */
function refreshBatch(client: QueryClient, id: number) {
  return Promise.all([
    client.invalidateQueries({ queryKey: keys.imports.detail(id) }),
    client.invalidateQueries({ queryKey: keys.imports.lists }),
  ]);
}

export interface SkipInput {
  rowId: number;
  skip: boolean;
}

export function useSkipRow(batchId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ rowId, skip }: SkipInput) =>
      apiFetch<ImportRow>(`/imports/${batchId}/rows/${rowId}/${skip ? 'skip' : 'unskip'}/`, {
        method: 'POST',
      }),
    onSuccess: () => refreshBatch(client, batchId),
  });
}

/** What an approve leaves to refresh: the batch, its rows, the directory and the dashboard. The
 * hook does this on success, and the review page after a polled approve (D72). */
export function afterApprove(client: QueryClient, batch: ImportBatch) {
  client.setQueryData(keys.imports.detail(batch.id), batch);
  return Promise.all([
    refreshBatch(client, batch.id),
    client.invalidateQueries({ queryKey: keys.employees.all }),
    client.invalidateQueries({ queryKey: keys.insights.all }),
  ]);
}

/** Approve. The live records changed, so the directory, the employee pages and the insights
 * refetch too. A refusal also refreshes the batch: the re-check may have re-marked rows. */
export function useApproveImport(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ImportBatch>(`/imports/${id}/approve/`, { method: 'POST' }),
    onSuccess: (batch) => {
      return afterApprove(client, batch);
    },
    onError: () => refreshBatch(client, id),
  });
}

export function useDiscardImport(id: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<ImportBatch>(`/imports/${id}/discard/`, { method: 'POST' }),
    onSuccess: (batch) => {
      client.setQueryData(keys.imports.detail(id), batch);
      return refreshBatch(client, id);
    },
  });
}
