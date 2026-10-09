import type { GridColDef, GridColumnVisibilityModel, GridRenderCellParams } from '@mui/x-data-grid';

import { Box, Button } from '@mui/material';

import type { EmployeeRow, ImportRow } from '../../api/types';
import { visuallyHidden } from '../../lib/a11y';
import { formatDate } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { RowMessagesCell, SheetCell } from '../imports/RowCells';
import { StatusChip } from '../layout/StatusChip';
import { EditLink } from './EditLink';

/** Why the record shown is not the one in force, in the API's order (SPEC F3): the employee has
 * left, else pay starts later. */
export function recordLabel(row: EmployeeRow): string {
  if (!row.shown) return 'no record';
  if (!row.shown.label) return 'current';
  if (row.status === 'exited' && row.last_date) return `exited ${formatDate(row.last_date)}`;
  return `from ${formatDate(row.shown.effective_from)}`;
}

/** A text cell its column may cut short with an ellipsis, with the full value as a native title on
 * hover, which adds no motion (D75). The cell keeps its own ellipsis. Numbers, amounts and dates
 * have room for their longest value and are never cut, so they carry none. */
export function titledText({ formattedValue }: Pick<GridRenderCellParams, 'formattedValue'>) {
  const text =
    formattedValue === null || formattedValue === undefined ? '' : String(formattedValue);
  return <span title={text}>{text}</span>;
}

/** Columns of the directory grid (DESIGN section 6). The money columns show whole units. With a
 * local currency the header names it, the one selected country's own. The widths of the columns
 * shown by default fit a 1280 px window without sideways scrolling (D63). */
export function directoryColumns(
  reportingCurrency: string,
  localCurrency?: string,
): GridColDef<EmployeeRow>[] {
  const reportingHeader =
    reportingCurrency === 'local'
      ? `Gross (${localCurrency ?? 'local currency'})`
      : `Gross (${reportingCurrency.toUpperCase()})`;
  return [
    {
      field: 'edit',
      headerName: 'Edit',
      width: 52,
      sortable: false,
      hideable: false,
      resizable: false,
      disableColumnMenu: true,
      renderHeader: () => (
        <Box component="span" sx={visuallyHidden}>
          Edit
        </Box>
      ),
      renderCell: ({ row, tabIndex }) => <EditLink row={row} tabIndex={tabIndex} />,
    },
    // Six digits whole: ACME-250000 takes 93 px at 14 px, with 20 px of padding.
    { field: 'employee_code', headerName: 'Code', width: 116 },
    {
      field: 'legacy_code',
      headerName: 'Legacy code',
      width: 130,
      sortable: false,
      valueGetter: (_value, row) => row.legacy_code ?? '',
    },
    { field: 'full_name', headerName: 'Name', flex: 1, minWidth: 138, renderCell: titledText },
    {
      field: 'email',
      headerName: 'Email',
      flex: 1,
      minWidth: 200,
      sortable: false,
      renderCell: titledText,
    },
    {
      field: 'department',
      headerName: 'Department',
      width: 136,
      valueGetter: (_value, row) => row.department.name,
      renderCell: titledText,
    },
    {
      field: 'country',
      headerName: 'Country',
      width: 124,
      valueGetter: (_value, row) => row.country.name,
    },
    { field: 'designation', headerName: 'Designation', width: 180, renderCell: titledText },
    { field: 'level', headerName: 'Level', type: 'number', width: 84 },
    {
      field: 'status',
      headerName: 'Status',
      width: 96,
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
      width: 136,
      valueGetter: (_value, row) => row.shown?.gross_reporting ?? null,
      valueFormatter: (value: string | null, row) =>
        value && row.shown ? formatMoney(value, row.shown.reporting_currency) : '',
    },
    {
      field: 'joining_date',
      headerName: 'Joined',
      width: 104,
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

/** Shown from the column chooser: what a 1280 px window has no room for (D63). */
export const DIRECTORY_HIDDEN_COLUMNS: GridColumnVisibilityModel = {
  legacy_code: false,
  email: false,
  designation: false,
  record: false,
  gross_local: false,
  last_date: false,
  effective_from: false,
  version: false,
};

const IDENTITY_WIDTHS: Record<string, number> = {
  email: 220,
  department: 130,
  designation: 160,
  level: 70,
  country_code: 110,
  gender: 100,
  joining_date: 120,
  last_date: 120,
  effective_from: 130,
  bonus_annual: 120,
};

interface ImportRowColumnOptions {
  /** Called with the row whose skip toggle was pressed. */
  onToggleSkip: (row: ImportRow) => void;
  /** False once the batch has left review. */
  canSkip: boolean;
}

/** Columns of the import review grid (DESIGN section 6): the skip toggle first, as the pencil
 * leads the directory, then the row, its status and its messages, then its action, the code and
 * the name, then every column the sheet had, as typed (the owner's order of 9 October, D75). Rows
 * come in sheet order, so nothing sorts. */
export function importRowColumns(
  sheetColumns: string[],
  { onToggleSkip, canSkip }: ImportRowColumnOptions,
): GridColDef<ImportRow>[] {
  const cell = (field: string, headerName: string, width: number): GridColDef<ImportRow> => ({
    field: `sheet:${field}`,
    headerName,
    width,
    sortable: false,
    valueGetter: (_value, row) => row.raw[field] ?? null,
    renderCell: ({ row }) => <SheetCell row={row} field={field} />,
  });
  return [
    {
      field: 'skip',
      headerName: 'Skip',
      width: 100,
      sortable: false,
      hideable: false,
      disableColumnMenu: true,
      renderCell: ({ row, tabIndex }) => {
        const skipped = row.status === 'skipped';
        return (
          <Button
            size="small"
            // The grid moves focus cell by cell; the button takes it only with its cell.
            tabIndex={tabIndex}
            disabled={!canSkip}
            aria-label={`${skipped ? 'Unskip' : 'Skip'} row ${row.row_number}`}
            onClick={() => onToggleSkip(row)}
          >
            {skipped ? 'Unskip' : 'Skip'}
          </Button>
        );
      },
    },
    { field: 'row_number', headerName: 'Row', width: 70, sortable: false, cellClassName: 'num' },
    {
      field: 'status',
      headerName: 'Status',
      width: 110,
      sortable: false,
      renderCell: ({ row }) => <StatusChip status={row.status} />,
    },
    {
      field: 'messages',
      headerName: 'Messages',
      width: 380,
      sortable: false,
      renderCell: ({ row }) => <RowMessagesCell row={row} />,
    },
    {
      field: 'action',
      headerName: 'Action',
      width: 100,
      sortable: false,
      renderCell: ({ row }) => (row.action ? <StatusChip status={row.action} /> : null),
    },
    cell('legacy_code', 'legacy_code', 130),
    cell('full_name', 'Name', 180),
    ...sheetColumns
      .filter((field) => field !== 'legacy_code' && field !== 'full_name')
      .map((field) => cell(field, field, IDENTITY_WIDTHS[field] ?? 120)),
  ];
}
