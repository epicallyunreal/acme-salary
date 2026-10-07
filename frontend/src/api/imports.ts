import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { saveFile } from '../lib/download';
import { apiDownload, apiFetch } from './client';
import { keys } from './keys';
import type { ImportBatch, Page } from './types';

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
      return client.invalidateQueries({ queryKey: [...keys.imports.all, 'list'] });
    },
  });
}

/** The XLSX template for one country, or for all of them when `country` is omitted. */
export async function downloadTemplate(country?: string) {
  const { blob, fileName } = await apiDownload('/imports/template/', { query: { country } });
  saveFile(blob, fileName ?? `acme-import-template${country ? `-${country}` : ''}.xlsx`);
}
