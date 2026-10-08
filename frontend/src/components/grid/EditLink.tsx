import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import { IconButton, Tooltip } from '@mui/material';
import { Link } from 'react-router';

import type { EmployeeRow } from '../../api/types';

/** The way into an employee from the directory (D63): a link named and titled for them. The grid
 * moves focus cell by cell, so the link takes it with its cell, and Enter follows it. */
export function EditLink({ row, tabIndex }: { row: EmployeeRow; tabIndex: 0 | -1 }) {
  const label = `Edit ${row.full_name}`;
  return (
    <Tooltip title={label}>
      <IconButton
        component={Link}
        to={`/employees/${row.id}`}
        size="small"
        aria-label={label}
        tabIndex={tabIndex}
      >
        <EditOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}
