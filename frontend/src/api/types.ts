// Hand-written mirrors of the serializer shapes (SPEC section 8, DESIGN 1.3). Money is a string.

export interface Me {
  id: number;
  email: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Country {
  code: string;
  name: string;
  currency_code: string;
  min_gross_annual?: string;
}

export interface Department {
  id?: number;
  code: string;
  name: string;
}

export type EmployeeStatus = 'active' | 'exited' | 'upcoming';
export type ReportingCurrency = 'usd' | 'eur' | 'local';

/** The record the directory shows: current on the reporting date, else the latest with a label. */
export interface ShownRecord {
  record_id: number;
  version: number;
  effective_from: string;
  effective_to: string | null;
  is_current: boolean;
  label: string | null;
  gross_local: string;
  currency_code: string;
  gross_reporting: string;
  reporting_currency: string;
}

export interface EmployeeRow {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  department: Pick<Department, 'code' | 'name'>;
  designation: string;
  level: number;
  country: Pick<Country, 'code' | 'name' | 'currency_code'>;
  status: EmployeeStatus;
  joining_date: string;
  last_date: string | null;
  shown: ShownRecord | null;
}

/** The query string of GET /employees/ (SPEC F4). Arrays join with commas on the wire. */
export type ListParams = {
  page?: number;
  page_size?: number;
  ordering?: string;
  search?: string;
  country?: string[];
  department?: string[];
  designation?: string[];
  level?: number[];
  status?: EmployeeStatus;
  gross_min?: string;
  gross_max?: string;
  joined_after?: string;
  joined_before?: string;
  currency?: ReportingCurrency;
};

export type ComponentKind = 'earning' | 'deduction' | 'employer_contribution';

/** GET /meta/components/?country=: the global components plus the country's own, in order. */
export interface SalaryComponent {
  id: number;
  code: string;
  name: string;
  kind: ComponentKind;
  country: string | null;
  sort_order: number;
}

/** A line as the API and the audit snapshot write it: the component's code (D34). */
export interface RecordLine {
  component: string;
  annual_amount: string;
}

/** Totals converted at read time by core/fx.py at the rate effective on the reporting date. */
export interface ConvertedTotals {
  currency: string;
  rate: string;
  rate_effective_from: string | null;
  bonus_annual: string;
  gross_annual: string;
  net_annual: string;
  total_cost_annual: string;
}

export interface CompensationRecord {
  id: number;
  employee: number;
  version: number;
  effective_from: string;
  /** Exclusive: the record ends the day before. Null while it is open-ended. */
  effective_to: string | null;
  is_current: boolean;
  is_scheduled: boolean;
  cancelled_at: string | null;
  cancelled_by: string | null;
  currency_code: string;
  bonus_annual: string;
  gross_annual: string;
  net_annual: string;
  total_cost_annual: string;
  source: 'ui' | 'import' | 'seed';
  note: string;
  created_at: string;
  created_by: string | null;
  lines: RecordLine[];
  converted: ConvertedTotals;
}

export type Gender = 'female' | 'male' | 'other' | 'undisclosed';

export interface EmployeeDetail {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  gender: Gender;
  department: Pick<Department, 'code' | 'name'>;
  designation: string;
  level: number;
  country: Pick<Country, 'code' | 'name' | 'currency_code'>;
  joining_date: string;
  last_date: string | null;
  status: EmployeeStatus;
  /** `from <date>` or `exited <date>` when the record shown is not current. */
  shown_label: string | null;
  current_record: CompensationRecord | null;
  created_at: string;
  updated_at: string;
}

/** A validator message; create and revise return the warnings beside the result (D27). */
export interface ServerMessage {
  field: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
}

export type WithWarnings<T> = T & { warnings: ServerMessage[] };

export type AuditAction =
  'create' | 'update' | 'exit' | 'revise' | 'cancel' | 'import_apply' | 'set_rate';

/** One audit row. `before` and `after` are the detail shapes, minus request-dependent keys. */
export interface AuditEntry {
  id: number;
  timestamp: string;
  actor: string | null;
  action: AuditAction;
  entity_type: 'employee' | 'compensation_record' | 'import_batch' | 'exchange_rate';
  entity_id: number;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  import_batch: number | null;
}

/** The history query string. The UI sends neither yet: the reporting-date picker is P1. */
export type HistoryParams = {
  on?: string;
  currency?: ReportingCurrency;
};

export interface ExitInput {
  last_date: string;
}

export interface LineInput {
  component: string;
  annual_amount: string;
}

/** POST /employees/{id}/compensation/. */
export interface RevisionInput {
  effective_from: string;
  bonus_annual?: string;
  note: string;
  lines: LineInput[];
}

/** POST /employees/. The code is assigned by the server; effective_from defaults to joining. */
export interface EmployeeCreateInput {
  full_name: string;
  email: string;
  gender: Gender;
  department: string;
  designation: string;
  level: number;
  country_code: string;
  joining_date: string;
  effective_from?: string;
  bonus_annual?: string;
  note: string;
  lines: LineInput[];
}

/** PATCH /employees/{id}/: only the identity fields that changed. */
export type IdentityPatch = Partial<
  Pick<
    EmployeeCreateInput,
    'full_name' | 'email' | 'gender' | 'department' | 'designation' | 'level' | 'joining_date'
  >
>;
