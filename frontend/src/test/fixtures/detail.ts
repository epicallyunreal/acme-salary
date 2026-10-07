import type { AuditEntry, CompensationRecord, EmployeeDetail, Page } from '../../api/types';
import { employees } from './employees';

// The four fixture people of employees.ts as the detail, history and audit endpoints return
// them on 7 October 2026. Dieter has a cancelled and a live revision on the same day (D43).

const HR = 'hr@acme.example';

type RecordFields = Pick<
  CompensationRecord,
  'id' | 'employee' | 'version' | 'effective_from' | 'currency_code' | 'gross_annual' | 'lines'
> &
  Partial<CompensationRecord>;

function record(fields: RecordFields): CompensationRecord {
  return {
    effective_to: null,
    is_current: false,
    is_scheduled: false,
    cancelled_at: null,
    cancelled_by: null,
    bonus_annual: '0.00',
    net_annual: fields.gross_annual,
    total_cost_annual: fields.gross_annual,
    source: 'ui',
    note: '',
    created_at: '2026-10-06T00:00:00+00:00',
    created_by: HR,
    converted: {
      currency: 'USD',
      rate: '1.00000000',
      rate_effective_from: null,
      bonus_annual: '0.00',
      gross_annual: fields.gross_annual,
      net_annual: fields.gross_annual,
      total_cost_annual: fields.gross_annual,
    },
    ...fields,
  };
}

const ashaRecord = record({
  id: 11,
  employee: 1,
  version: 1,
  effective_from: '2020-01-01',
  is_current: true,
  currency_code: 'INR',
  bonus_annual: '50000.00',
  gross_annual: '1450000.00',
  net_annual: '1250000.00',
  total_cost_annual: '1570000.00',
  note: 'offer',
  lines: [
    { component: 'BASE', annual_amount: '1000000.00' },
    { component: 'HRA', annual_amount: '400000.00' },
    { component: 'TAX', annual_amount: '200000.00' },
    { component: 'EMPLOYER_CONTRIBUTION', annual_amount: '120000.00' },
  ],
  converted: {
    currency: 'USD',
    rate: '0.01200000',
    rate_effective_from: '2026-10-01',
    bonus_annual: '600.00',
    gross_annual: '17400.00',
    net_annual: '15000.00',
    total_cost_annual: '18840.00',
  },
});

const benRecord = record({
  id: 21,
  employee: 2,
  version: 1,
  effective_from: '2018-06-15',
  is_current: true,
  currency_code: 'USD',
  gross_annual: '100000.00',
  lines: [{ component: 'BASE', annual_amount: '100000.00' }],
});

const chloeRecord = record({
  id: 31,
  employee: 3,
  version: 1,
  effective_from: '2022-03-01',
  effective_to: '2026-07-01',
  currency_code: 'GBP',
  gross_annual: '80000.00',
  lines: [{ component: 'BASE', annual_amount: '80000.00' }],
  converted: {
    currency: 'USD',
    rate: '1.34500000',
    rate_effective_from: '2026-10-01',
    bonus_annual: '0.00',
    gross_annual: '107600.00',
    net_annual: '107600.00',
    total_cost_annual: '107600.00',
  },
});

function germanLines(base: string, share: string) {
  return [
    { component: 'BASE', annual_amount: base },
    { component: 'TAX', annual_amount: share },
    { component: 'SOCIAL_INSURANCE', annual_amount: share },
    { component: 'EMPLOYER_CONTRIBUTION', annual_amount: share },
  ];
}

const dieterCurrent = record({
  id: 41,
  employee: 4,
  version: 1,
  effective_from: '2023-09-01',
  effective_to: '2026-11-01',
  is_current: true,
  currency_code: 'EUR',
  gross_annual: '60000.00',
  net_annual: '36000.00',
  total_cost_annual: '72000.00',
  lines: germanLines('60000.00', '12000.00'),
  converted: {
    currency: 'USD',
    rate: '1.17500000',
    rate_effective_from: '2026-10-01',
    bonus_annual: '0.00',
    gross_annual: '70500.00',
    net_annual: '42300.00',
    total_cost_annual: '84600.00',
  },
});

const dieterCancelled = record({
  id: 42,
  employee: 4,
  version: 2,
  effective_from: '2026-11-01',
  currency_code: 'EUR',
  gross_annual: '64000.00',
  note: 'annual raise',
  cancelled_at: '2026-10-05T10:00:00+00:00',
  cancelled_by: HR,
  lines: germanLines('64000.00', '12800.00'),
});

const dieterScheduled = record({
  id: 43,
  employee: 4,
  version: 3,
  effective_from: '2026-11-01',
  is_scheduled: true,
  currency_code: 'EUR',
  gross_annual: '66000.00',
  note: 'annual raise, corrected',
  lines: germanLines('66000.00', '13200.00'),
});

function detail(
  index: number,
  current: CompensationRecord,
  extra: Partial<EmployeeDetail> = {},
): EmployeeDetail {
  const row = employees[index];
  return {
    id: row.id,
    employee_code: row.employee_code,
    full_name: row.full_name,
    email: row.email,
    department: row.department,
    designation: row.designation,
    level: row.level,
    country: row.country,
    status: row.status,
    joining_date: row.joining_date,
    last_date: row.last_date,
    gender: 'female',
    shown_label: null,
    current_record: current,
    created_at: '2026-10-06T00:00:00+00:00',
    updated_at: '2026-10-06T00:00:00+00:00',
    ...extra,
  };
}

export const employeeDetails: Record<number, EmployeeDetail> = {
  1: detail(0, ashaRecord),
  2: detail(1, benRecord, { gender: 'male' }),
  3: detail(2, chloeRecord, { shown_label: 'exited 2026-06-30' }),
  4: detail(3, dieterCurrent, { gender: 'male' }),
};

export const histories: Record<number, CompensationRecord[]> = {
  1: [ashaRecord],
  2: [benRecord],
  3: [chloeRecord],
  4: [dieterScheduled, dieterCancelled, dieterCurrent],
};

const audits: Record<number, AuditEntry[]> = {
  1: [
    {
      id: 3,
      timestamp: '2026-10-07T09:00:00+00:00',
      actor: HR,
      action: 'update',
      entity_type: 'employee',
      entity_id: 1,
      before: { designation: 'Engineer', level: 2 },
      after: { designation: 'Senior Engineer', level: 3 },
      import_batch: null,
    },
    {
      id: 2,
      timestamp: '2026-10-06T00:00:00+00:00',
      actor: null,
      action: 'create',
      entity_type: 'employee',
      entity_id: 1,
      before: null,
      after: { employee_code: 'ACME-000001' },
      import_batch: null,
    },
    {
      id: 1,
      timestamp: '2026-10-06T00:00:00+00:00',
      actor: null,
      action: 'revise',
      entity_type: 'compensation_record',
      entity_id: 11,
      before: null,
      after: {
        version: 1,
        effective_from: '2020-01-01',
        gross_annual: '1450000.00',
        currency_code: 'INR',
      },
      import_batch: null,
    },
  ],
};

export function auditPage(employeeId: number): Page<AuditEntry> {
  const results = audits[employeeId] ?? [];
  return { count: results.length, next: null, previous: null, results };
}
