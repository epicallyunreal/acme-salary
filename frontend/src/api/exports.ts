import { saveFile } from '../lib/download';
import { apiDownload } from './client';
import { insightQuery } from './insights';
import type { InsightControl, InsightName, InsightParams, ListParams } from './types';

export type ExportFile = 'csv' | 'xlsx' | 'json';

/** The formats every export offers, in menu order (SPEC F6). */
export const EXPORT_FILES: readonly ExportFile[] = ['csv', 'xlsx', 'json'];

/** Every employee the directory's filters, search and sort leave, not just the page on screen
 * (SPEC F6). The file is fetched with the bearer token and saved from a blob. */
export async function exportEmployees(params: ListParams, file: ExportFile) {
  const query = { ...params, page: undefined, page_size: undefined, file };
  const { blob, fileName } = await apiDownload('/exports/employees/', { query });
  saveFile(blob, fileName ?? `acme-employees.${file}`);
}

/** One insight's table for the dashboard's filters and the card's control, the card's figures in
 * rows (D60, D62). */
export async function exportInsight(
  name: InsightName,
  params: InsightParams,
  file: ExportFile,
  control: InsightControl = {},
) {
  const query = { ...insightQuery(params), ...control, file };
  const { blob, fileName } = await apiDownload(`/exports/insights/${name}/`, { query });
  saveFile(blob, fileName ?? `acme-${name}.${file}`);
}
