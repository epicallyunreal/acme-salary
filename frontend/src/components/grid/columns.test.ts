import { describe, expect, it } from 'vitest';

import { DIRECTORY_HIDDEN_COLUMNS, directoryColumns } from './columns';

// A 1280 px window less AppShell's 208 px nav, the page's 24 px padding each side, the grid's two
// 1 px borders, and two 17 px scrollbars where scrollbars take room: the grid's own, and main's
// once the window is shorter than the grid's floor (D63, D75).
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

  it('keeps the pencil out of the chooser and out of sorting', () => {
    const [edit] = directoryColumns('usd');

    expect([edit.field, edit.hideable, edit.sortable]).toEqual(['edit', false, false]);
  });
});
