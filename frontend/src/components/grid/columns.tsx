import type { GridColDef, GridColumnVisibilityModel } from '@mui/x-data-grid';

import type { EmployeeRow } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { StatusChip } from '../layout/StatusChip';

/** "from 2027-01-01" and "exited 2026-06-30" from the API, with the date written out. */
export function recordLabel(row: EmployeeRow): string {
  if (!row.shown) return 'no record';
  if (!row.shown.label) return 'current';
  const [word, date] = row.shown.label.split(' ');
  return `${word} ${formatDate(date)}`;
}

/** Columns of the directory grid (DESIGN section 6). The money columns show whole units. */
export function directoryColumns(reportingCurrency: string): GridColDef<EmployeeRow>[] {
  const reportingHeader =
    reportingCurrency === 'local'
      ? 'Gross (local currency)'
      : `Gross (${reportingCurrency.toUpperCase()})`;
  return [
    { field: 'employee_code', headerName: 'Code', width: 110 },
    {
      field: 'legacy_code',
      headerName: 'Legacy code',
      width: 130,
      sortable: false,
      valueGetter: (_value, row) => row.legacy_code ?? '',
    },
    { field: 'full_name', headerName: 'Name', flex: 1, minWidth: 160 },
    { field: 'email', headerName: 'Email', flex: 1, minWidth: 200, sortable: false },
    {
      field: 'department',
      headerName: 'Department',
      width: 140,
      valueGetter: (_value, row) => row.department.name,
    },
    {
      field: 'country',
      headerName: 'Country',
      width: 130,
      valueGetter: (_value, row) => row.country.name,
    },
    { field: 'designation', headerName: 'Designation', width: 180 },
    { field: 'level', headerName: 'Level', type: 'number', width: 80 },
    {
      field: 'status',
      headerName: 'Status',
      width: 110,
      sortable: false,
      renderCell: ({ value }) => <StatusChip status={String(value)} />,
    },
    {
      field: 'record',
      headerName: 'Record',
      width: 150,
      sortable: false,
      valueGetter: (_value, row) => recordLabel(row),
    },
    {
      field: 'gross_local',
      headerName: 'Gross (local)',
      type: 'number',
      width: 160,
      sortable: false,
      valueGetter: (_value, row) => row.shown?.gross_local ?? null,
      valueFormatter: (value: string | null, row) =>
        value && row.shown ? formatMoney(value, row.shown.currency_code) : '',
    },
    {
      field: 'gross_reporting',
      headerName: reportingHeader,
      type: 'number',
      width: 160,
      valueGetter: (_value, row) => row.shown?.gross_reporting ?? null,
      valueFormatter: (value: string | null, row) =>
        value && row.shown ? formatMoney(value, row.shown.reporting_currency) : '',
    },
    {
      field: 'joining_date',
      headerName: 'Joined',
      width: 120,
      valueFormatter: (value: string) => formatDate(value),
    },
    {
      field: 'last_date',
      headerName: 'Last day',
      width: 120,
      sortable: false,
      valueFormatter: (value: string | null) => formatDate(value),
    },
    {
      field: 'effective_from',
      headerName: 'Effective from',
      width: 130,
      sortable: false,
      valueGetter: (_value, row) => row.shown?.effective_from ?? null,
      valueFormatter: (value: string | null) => formatDate(value),
    },
    {
      field: 'version',
      headerName: 'Version',
      type: 'number',
      width: 90,
      sortable: false,
      valueGetter: (_value, row) => row.shown?.version ?? null,
    },
  ];
}

export const DIRECTORY_HIDDEN_COLUMNS: GridColumnVisibilityModel = {
  legacy_code: false,
  email: false,
  last_date: false,
  version: false,
};
