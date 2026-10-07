import type { ImportBatch, Page } from '../../api/types';

const HR = 'hr@acme.example';

type BatchFields = Pick<ImportBatch, 'id' | 'file_name' | 'status'> & Partial<ImportBatch>;

function batch(fields: BatchFields): ImportBatch {
  return {
    file_size: 20480,
    uploaded_by: HR,
    uploaded_at: '2026-10-07T09:12:00+00:00',
    warnings: [],
    total_rows: 0,
    valid_rows: 0,
    warning_rows: 0,
    error_rows: 0,
    skipped_rows: 0,
    noop_rows: 0,
    created_rows: 0,
    updated_rows: 0,
    revised_rows: 0,
    applied_rows: 0,
    approved_at: null,
    error_summary: '',
    ...fields,
  };
}

/** In review: five rows, one each valid, warning, error, skipped and no-op (DESIGN section 9).
 * The no-op row counts as valid too. */
export const reviewBatch = batch({
  id: 3,
  file_name: 'october-raises.xlsx',
  status: 'review',
  warnings: ['Ignored unknown column: Remarks'],
  total_rows: 5,
  valid_rows: 2,
  warning_rows: 1,
  error_rows: 1,
  skipped_rows: 1,
  noop_rows: 1,
});

export const approvedBatch = batch({
  id: 2,
  file_name: 'new-joiners.csv',
  status: 'approved',
  uploaded_at: '2026-10-06T17:40:00+00:00',
  total_rows: 12,
  valid_rows: 12,
  created_rows: 12,
  applied_rows: 12,
  approved_at: '2026-10-06T17:45:00+00:00',
});

export const discardedBatch = batch({
  id: 1,
  file_name: 'bad-headers.xlsx',
  status: 'discarded',
  uploaded_at: '2026-10-06T17:31:00+00:00',
  total_rows: 4,
  valid_rows: 1,
  error_rows: 3,
});

export const batches: ImportBatch[] = [reviewBatch, approvedBatch, discardedBatch];

export function batchPage(results: ImportBatch[] = batches): Page<ImportBatch> {
  return { count: results.length, next: null, previous: null, results };
}
