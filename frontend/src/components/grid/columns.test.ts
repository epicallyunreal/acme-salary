import { describe, expect, it } from 'vitest';

import {
  DIRECTORY_HIDDEN_COLUMNS,
  directoryColumns,
  importRowColumns,
  titledText,
} from './columns';

// A 1280 px window less AppShell's 208 px nav, the page's 24 px padding each side, the grid's two
// 1 px borders, and two 17 px scrollbars where scrollbars take room: the grid's own, and main's
// when the page is taller than the window (D63, D75).
const WIDTH_AT_1280 = 1280 - 208 - 2 * 24 - 2 - 2 * 17;

describe('directoryColumns', () => {
  it('shows by default only the columns that fit a 1280 px window without sideways scrolling', () => {
    const shown = directoryColumns('usd').filter(
      (column) => DIRECTORY_HIDDEN_COLUMNS[column.field] !== false,
    );
    const width = shown.reduce(
      (sum, column) => sum + (column.flex ? (column.minWidth ?? 0) : (column.width ?? 100)),
      0,
    );

    expect(shown.map((column) => column.field)).toEqual([
      'edit',
      'employee_code',
      'full_name',
      'department',
      'country',
      'level',
      'status',
      'gross_reporting',
      'joining_date',
    ]);
    expect(width).toBeLessThanOrEqual(WIDTH_AT_1280);
  });

  it('gives each text cell that can be cut short its full value on hover, and no number', () => {
    const columns = directoryColumns('usd');
    const titled = columns.filter((column) => column.renderCell === titledText);

    expect(titled.map((column) => column.field)).toEqual([
      'full_name',
      'email',
      'department',
      'designation',
    ]);
    const cell = titledText({ formattedValue: 'Principal Financial Analyst, Treasury' });
    expect(cell.props).toMatchObject({
      title: 'Principal Financial Analyst, Treasury',
      children: 'Principal Financial Analyst, Treasury',
    });
    expect(titledText({ formattedValue: null }).props.title).toBe('');
  });

  it('keeps the pencil out of the chooser and out of sorting', () => {
    const [edit] = directoryColumns('usd');

    expect([edit.field, edit.hideable, edit.sortable]).toEqual(['edit', false, false]);
  });
});

describe('importRowColumns', () => {
  it('leads with Skip, as the pencil leads the directory, and puts Messages after Status (D75)', () => {
    const columns = importRowColumns(['legacy_code', 'full_name', 'email', 'BASE'], {
      onToggleSkip: () => undefined,
      canSkip: true,
    });

    expect(columns.map((column) => column.field)).toEqual([
      'skip',
      'row_number',
      'status',
      'messages',
      'action',
      'sheet:legacy_code',
      'sheet:full_name',
      'sheet:email',
      'sheet:BASE',
    ]);
    // Like the pencil, the toggle is never hidden from the chooser nor given a column menu.
    expect([columns[0].hideable, columns[0].disableColumnMenu]).toEqual([false, true]);
  });
});
