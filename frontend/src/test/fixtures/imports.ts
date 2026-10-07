import type { CellValue, ImportBatch, ImportRow, Page, RowMessage } from '../../api/types';

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

const SHEET = [
  'legacy_code',
  'full_name',
  'email',
  'department',
  'designation',
  'level',
  'country_code',
  'gender',
  'joining_date',
  'last_date',
  'effective_from',
  'bonus_annual',
  'BASE',
  'HRA',
  'ALLOWANCES',
  'TAX',
  'EMPLOYER_CONTRIBUTION',
] as const;

function raw(cells: Partial<Record<(typeof SHEET)[number], CellValue>>): Record<string, CellValue> {
  return Object.fromEntries(SHEET.map((column) => [column, cells[column] ?? null]));
}

type RowFields = Pick<ImportRow, 'id' | 'row_number' | 'status' | 'action'> & {
  cells: Partial<Record<(typeof SHEET)[number], CellValue>>;
  messages: RowMessage[];
  matched?: number;
};

function row({ id, row_number, status, action, cells, messages, matched }: RowFields): ImportRow {
  return {
    id,
    row_number,
    legacy_code: String(cells.legacy_code ?? ''),
    full_name: String(cells.full_name ?? ''),
    status,
    validation_status: status === 'skipped' ? 'error' : status,
    action,
    messages,
    matched_employee: matched ? { id: matched, employee_code: `ACME-${matched}` } : null,
    raw: raw(cells),
    normalized: {},
  };
}

const INDIA = {
  department: 'engineering',
  designation: 'Engineer',
  level: 2,
  country_code: 'IN',
  gender: 'female',
  joining_date: '2024-03-01',
  HRA: 360000,
  TAX: 90000,
};

/** reviewBatch's rows in sheet order: valid, warning, error, skipped and no-op. */
export const reviewRows: ImportRow[] = [
  row({
    id: 31,
    row_number: 2,
    status: 'valid',
    action: 'create',
    cells: {
      ...INDIA,
      legacy_code: 'HR-20001',
      full_name: 'Meera Iyer',
      email: 'meera@acme.example',
      joining_date: '2026-11-01',
      BASE: 900000,
    },
    messages: [
      {
        field: 'effective_from',
        severity: 'info',
        message: 'effective_from defaulted to joining_date 2026-11-01',
      },
    ],
  }),
  row({
    id: 32,
    row_number: 3,
    status: 'warning',
    action: 'revise',
    matched: 41,
    cells: {
      ...INDIA,
      legacy_code: 'HR-41207',
      full_name: 'Mohan Khan',
      email: 'mohan@acme.example',
      effective_from: '2026-11-01',
      BASE: 250000,
    },
    messages: [
      {
        field: 'gross',
        severity: 'warning',
        message: 'gross 300,000 INR is below the India minimum 400,000',
      },
    ],
  }),
  row({
    id: 33,
    row_number: 4,
    status: 'error',
    action: 'revise',
    matched: 17,
    cells: {
      ...INDIA,
      legacy_code: 'HR-58213',
      full_name: 'Ravi Iyer',
      email: 'ravi@acme.example',
      effective_from: '2026-11-01',
      BASE: '-5000',
    },
    messages: [
      {
        field: 'BASE',
        severity: 'error',
        message: 'BASE must be a non-negative number, got -5000',
      },
    ],
  }),
  row({
    id: 34,
    row_number: 5,
    status: 'skipped',
    action: null,
    cells: { ...INDIA, full_name: 'No Code', email: 'nocode@acme.example', BASE: 500000 },
    messages: [{ field: 'legacy_code', severity: 'error', message: 'legacy_code is required' }],
  }),
  row({
    id: 35,
    row_number: 6,
    status: 'valid',
    action: 'noop',
    matched: 23,
    cells: {
      ...INDIA,
      legacy_code: 'HR-77310',
      full_name: 'Lata Rao',
      email: 'lata@acme.example',
      BASE: 700000,
    },
    messages: [
      { field: 'row', severity: 'info', message: 'No changes, row will be skipped on apply' },
    ],
  }),
];

/** reviewRows filtered and paged the way the API does it. */
export function rowsPage(url: URL, rows: ImportRow[] = reviewRows): Page<ImportRow> {
  const statuses = (url.searchParams.get('status') ?? '').split(',').filter(Boolean);
  const search = (url.searchParams.get('search') ?? '').toLowerCase();
  const page = Number(url.searchParams.get('page') ?? '1');
  const size = Number(url.searchParams.get('page_size') ?? '25');
  const matching = rows.filter(
    (candidate) =>
      (!statuses.length || statuses.includes(candidate.status)) &&
      (!search ||
        candidate.legacy_code.toLowerCase().includes(search) ||
        candidate.full_name.toLowerCase().includes(search)),
  );
  return {
    count: matching.length,
    next: page * size < matching.length ? 'next' : null,
    previous: page > 1 ? 'previous' : null,
    results: matching.slice((page - 1) * size, page * size),
  };
}
