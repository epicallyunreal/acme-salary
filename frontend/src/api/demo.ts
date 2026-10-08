import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { saveFile } from '../lib/download';
import { apiDownload, apiFetch } from './client';
import { keys } from './keys';
import type { ResetCounts, ResetInput, SampleFiles } from './types';

export function listSampleFiles(): Promise<SampleFiles> {
  return apiFetch<SampleFiles>('/admin/sample-files/');
}

/** The seven files of SPEC F9 with a line on what each exercises, the generated ones unavailable
 * while the database is empty (D72). */
export function useSampleFiles() {
  return useQuery({ queryKey: keys.demo.files, queryFn: listSampleFiles });
}

/** One sample file, the base one from disk and the rest generated from the live tables on the
 * server, saved under the name the API gives it. */
export async function downloadSampleFile(name: string, fileName: string) {
  const { blob, fileName: named } = await apiDownload(`/admin/sample-files/${name}/`);
  saveFile(blob, named ?? fileName);
}

export function getResetCounts(): Promise<ResetCounts> {
  return apiFetch<ResetCounts>('/admin/reset-demo/');
}

/** What a reset would delete, read when the dialog opens. */
export function useResetCounts(enabled: boolean) {
  return useQuery({ queryKey: keys.demo.counts, queryFn: getResetCounts, enabled });
}

export function resetDemo(input: ResetInput): Promise<ResetCounts> {
  return apiFetch<ResetCounts>('/admin/reset-demo/', { method: 'POST', body: input });
}

/** Empties the database. Every cached query is dropped afterwards, since nothing it held is true
 * any more. */
export function useResetDemo() {
  const client = useQueryClient();
  return useMutation({ mutationFn: resetDemo, onSuccess: () => client.clear() });
}
