import { Box, Pagination, TextField, Typography } from '@mui/material';
import type { TablePaginationActionsProps } from '@mui/material/TablePaginationActions';
import { type KeyboardEvent, useId, useState } from 'react';

/** The pages there are: one at least, so an empty grid still shows page 1. */
function pageCount(count: number, rowsPerPage: number): number {
  return Math.max(1, Math.ceil(count / rowsPerPage));
}

/** The page a typed number asks for, clamped to the pages there are, or null for no number. */
function wantedPage(typed: string, pages: number): number | null {
  const wanted = Number.parseInt(typed, 10);
  if (Number.isNaN(wanted)) return null;
  return Math.min(Math.max(wanted, 1), pages);
}

/**
 * The pager's actions as numbered pages (DESIGN section 6, D64): the first and the last page, the
 * current one and its neighbours, ellipses between, and a Go to page field that jumps on Enter to
 * the page asked for, or the nearest there is. The grid's own pager keeps Rows per page and
 * `1–25 of 10,000` beside it, and the page it reports goes to the URL like any other.
 */
export function PageNumbers({
  count,
  page,
  rowsPerPage,
  onPageChange,
  disabled,
  className,
}: TablePaginationActionsProps) {
  const pages = pageCount(count, rowsPerPage);
  const [typed, setTyped] = useState('');
  const fieldId = useId();

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const wanted = wantedPage(typed, pages);
    if (wanted === null) return;
    setTyped('');
    if (wanted - 1 !== page) onPageChange(null, wanted - 1);
  };

  return (
    <Box className={className} sx={{ display: 'flex', alignItems: 'center', gap: 2, ml: 2 }}>
      <Pagination
        count={pages}
        page={page + 1}
        onChange={(_, value) => onPageChange(null, value - 1)}
        boundaryCount={1}
        siblingCount={1}
        disabled={disabled}
        size="small"
        shape="rounded"
      />
      <Box sx={{ display: { xs: 'none', sm: 'flex' }, alignItems: 'center', gap: 1 }}>
        <Typography
          component="label"
          htmlFor={fieldId}
          variant="body2"
          sx={{ whiteSpace: 'nowrap' }}
        >
          Go to page
        </Typography>
        <TextField
          id={fieldId}
          type="number"
          size="small"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabled}
          slotProps={{ htmlInput: { min: 1, max: pages, step: 1 } }}
          sx={{ width: 80 }}
        />
      </Box>
    </Box>
  );
}
