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
/** The directory's Status filter: one status, or `any` for everyone (D64). */
export type DirectoryStatus = EmployeeStatus | 'any';
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
  /** ACME-<id>, numbered by the database (D48). */
  employee_code: string;
  /** The code the legacy system gave an imported employee; null when added in the app. */
  legacy_code: string | null;
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
  status?: DirectoryStatus;
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
  /** ACME-<id>, numbered by the database (D48). */
  employee_code: string;
  /** The code the legacy system gave an imported employee; null when added in the app. */
  legacy_code: string | null;
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

// Imports (SPEC section 5 "ImportBatch and ImportRow", section 8)

export type BatchStatus = 'review' | 'approved' | 'discarded' | 'failed';
export type RowStatus = 'valid' | 'warning' | 'error' | 'skipped';
export type RowAction = 'create' | 'update' | 'revise' | 'noop';

export interface ImportBatch {
  id: number;
  file_name: string;
  file_size: number;
  uploaded_by: string | null;
  uploaded_at: string;
  status: BatchStatus;
  /** Batch-level warnings, such as `Ignored unknown column: Remarks`. */
  warnings: string[];
  total_rows: number;
  /** No-op rows count as valid too; a skipped row counts only as skipped. */
  valid_rows: number;
  warning_rows: number;
  error_rows: number;
  skipped_rows: number;
  noop_rows: number;
  created_rows: number;
  updated_rows: number;
  revised_rows: number;
  applied_rows: number;
  approved_at: string | null;
  error_summary: string;
}

export interface RowMessage {
  /** A template column (`BASE`, `email`) or `row` for the row as a whole. */
  field: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
}

/** The API sends a cell as text, so numbers keep the digits the user typed. */
export type CellValue = string | boolean | null;

export interface ImportRow {
  id: number;
  row_number: number;
  legacy_code: string;
  full_name: string;
  status: RowStatus;
  validation_status: Exclude<RowStatus, 'skipped'>;
  /** Null when the row names no usable employee code. */
  action: RowAction | null;
  messages: RowMessage[];
  matched_employee: { id: number; employee_code: string } | null;
  /** The cells as the sheet had them, by template column. */
  raw: Record<string, CellValue>;
}

export interface ImportRowParams {
  page: number;
  page_size: number;
  /** Comma-separated row statuses. */
  status?: string;
  search?: string;
}

// Insights (DESIGN 1.6). Money is a two-decimal string, or null where SPEC section 9 withholds it.

export type InsightName =
  | 'summary'
  | 'by-country'
  | 'by-department'
  | 'distribution'
  | 'by-level'
  | 'gender-gap'
  | 'trend'
  | 'cost-bridge'
  | 'by-tenure'
  | 'cost-mix';

/** A card's own control on the wire, `{ measure: 'headcount' }`: what it measures or how it
 * slices, never who is counted (D62). */
export type InsightControl = Record<string, string>;

export interface InsightParams {
  country: string[];
  department: string[];
  currency: ReportingCurrency;
  include_exited: boolean;
  /** The period's first and last days, both counted (D64). */
  from: string;
  to: string;
}

export interface RateMonth {
  label: string;
  effective_from: string | null;
}

/** Every payload names its period. Trend and the bridge move over it, every other card shows the
 * state on `to`, and one rate, in force on `to`, converts every date (D64). */
interface InsightHeader {
  from: string;
  to: string;
  currency: string;
  rate_month: RateMonth;
}

export interface SummaryInsight extends InsightHeader {
  headcount: number;
  total_cost: string | null;
  mean_gross: string | null;
  median_gross: string | null;
  countries: number;
  departments: number;
  /** What the period cost, each record's annual total cost pro-rated by the days it was in force,
   * and everyone employed on any day of it, the total `null` under five of them (D64). */
  spent: { headcount: number; total_cost: string | null };
}

export interface CountryRow {
  country: { code: string; name: string };
  headcount: number;
  total_cost: string | null;
  median_gross: string | null;
  share_pct: string | null;
}

export interface DepartmentRow {
  department: { code: string; name: string };
  headcount: number;
  total_cost: string | null;
  mean_gross: string | null;
  median_gross: string | null;
}

export interface Band {
  index: number;
  from: string;
  to: string;
  count: number;
}

export interface DistributionInsight extends InsightHeader {
  headcount: number;
  p1: string | null;
  p99: string | null;
  bands: Band[] | null;
  markers: { p10: string; p50: string; p90: string } | null;
}

/** p10 to p90, never min or max, and only for twenty people or more (D59). */
export interface LevelRow {
  level: number;
  headcount: number;
  p10: string | null;
  p25: string | null;
  median: string | null;
  p75: string | null;
  p90: string | null;
}

export interface GenderGroup {
  headcount: number;
  median_gross: string | null;
}

export interface GapRow {
  country: { code: string; name: string } | null;
  female: GenderGroup;
  male: GenderGroup;
  other_count: number;
  undisclosed_count: number;
  gap_pct: string | null;
  reason: string | null;
}

export type TrendMeasure = 'total_cost' | 'headcount';

export interface TrendPoint {
  date: string;
  headcount: number;
  total_cost: string | null;
}

/** Headcount and total cost on `from`, each month-end between and `to`, at one rate (D64). */
export interface TrendInsight extends InsightHeader {
  measure: TrendMeasure;
  points: TrendPoint[];
}

export type BridgePartName = 'start' | 'leavers' | 'joiners' | 'pay_changes' | 'end';

export interface BridgePart {
  part: BridgePartName;
  people: number;
  /** Leavers are negative. `null` when withheld, with the reason (D62). */
  amount: string | null;
  reason: string | null;
}

/** Why total cost moved from `from` to `to`, the parts adding up exactly (D64). */
export interface CostBridgeInsight extends InsightHeader {
  start_date: string;
  end_date: string;
  parts: BridgePart[];
}

export interface TenureRow {
  band: 'under_1' | '1_to_3' | '3_to_5' | '5_to_10' | '10_plus';
  label: string;
  headcount: number;
  median_gross: string | null;
}

/** Median gross by completed years of service, within one level or all of them (D62). */
export interface ByTenureInsight extends InsightHeader {
  level: string;
  rows: TenureRow[];
}

export interface MixSegment {
  code: string;
  name: string;
  share_pct: string;
}

export interface MixRow {
  country: { code: string; name: string };
  headcount: number;
  /** `null` under five people, or when a segment is held by 1 to 4 of them, with the reason
   * (D62). */
  segments: MixSegment[] | null;
  reason: string | null;
}

export type MixView = 'cost' | 'take_home';

/** One bar per country: shares of total cost, or of gross split into net and deductions (D62). */
export interface CostMixInsight extends InsightHeader {
  view: MixView;
  /** Every segment of the bars shown, in the one order they stack. */
  segments: { code: string; name: string }[];
  rows: MixRow[];
}

export type GenderView = 'pay_gap' | 'bonus' | 'quartiles' | 'by_level';

export interface PayGapInsight extends InsightHeader {
  view: 'pay_gap';
  rows: GapRow[];
}

export interface BonusSide {
  headcount: number;
  /** `null` with the group's reason when there are fewer than 5 women or men in it. */
  receiving: number | null;
  receiving_pct: string | null;
  /** `null` too when fewer than 5 women or men receive one. No mean amount is published (D62). */
  median_bonus: string | null;
}

export interface BonusRow {
  country: { code: string; name: string } | null;
  female: BonusSide;
  male: BonusSide;
  other_count: number;
  undisclosed_count: number;
  mean_gap_pct: string | null;
  median_gap_pct: string | null;
  reason: string | null;
}

export interface BonusInsight extends InsightHeader {
  view: 'bonus';
  rows: BonusRow[];
}

export interface Quartile {
  quartile: number;
  headcount: number;
  female: number;
  male: number;
  female_pct: string;
  male_pct: string;
}

/** Women and men ranked by pay. Other and undisclosed are counted beside, never ranked (D62). */
export interface QuartilesInsight extends InsightHeader {
  view: 'quartiles';
  /** The women and men ranked. */
  headcount: number;
  other_count: number;
  undisclosed_count: number;
  /** `null` under 20 people, or under 5 women or men, with the reason. */
  quartiles: Quartile[] | null;
  reason: string | null;
}

export interface LevelSide {
  headcount: number;
  median_gross: string | null;
}

export interface LevelGapRow {
  country: { code: string; name: string };
  level: number;
  female: LevelSide;
  male: LevelSide;
  mean_gap_pct: string | null;
  median_gap_pct: string | null;
  /** A mean gap of 5% or more either way, EU Directive 2023/970 Article 10's threshold. */
  flagged: boolean;
  reason: string | null;
}

export interface LevelOthers {
  country: { code: string; name: string };
  other_count: number;
  undisclosed_count: number;
}

export interface LevelGapsInsight extends InsightHeader {
  view: 'by_level';
  rows: LevelGapRow[];
  /** Counted per country beside the levels, never per level (D62). */
  others: LevelOthers[];
}

/** The gender gap on annual pay, in the view the card's control picks (D62). */
export type GenderGapInsight = PayGapInsight | BonusInsight | QuartilesInsight | LevelGapsInsight;

export interface InsightPayloads {
  summary: SummaryInsight;
  'by-country': InsightHeader & { rows: CountryRow[] };
  'by-department': InsightHeader & { rows: DepartmentRow[] };
  distribution: DistributionInsight;
  'by-level': InsightHeader & { rows: LevelRow[] };
  'gender-gap': GenderGapInsight;
  trend: TrendInsight;
  'cost-bridge': CostBridgeInsight;
  'by-tenure': ByTenureInsight;
  'cost-mix': CostMixInsight;
}

export interface ExchangeRates {
  on: string;
  rates: { from_currency: string; to_currency: string; rate: string; effective_from: string }[];
  month_labels: Record<string, string>;
}
