import type { ImportBatch } from '../../api/types';

/** The rows approve would apply: valid and warning rows that are not skipped or no-ops. */
export function applicableRows(batch: ImportBatch) {
  return batch.valid_rows + batch.warning_rows - batch.noop_rows;
}

export function rowsWord(count: number) {
  return `${count.toLocaleString('en-US')} ${count === 1 ? 'row' : 'rows'}`;
}
