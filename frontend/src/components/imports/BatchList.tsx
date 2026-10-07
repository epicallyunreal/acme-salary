import {
  Link,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material';
import { Link as RouterLink } from 'react-router';

import type { ImportBatch } from '../../api/types';
import { formatDateTime } from '../../lib/dates';
import { StatusChip } from '../layout/StatusChip';

const PAGE_SIZE = 25;

interface BatchListProps {
  batches: ImportBatch[];
  count: number;
  page: number;
  onPageChange: (page: number) => void;
}

function count(value: number) {
  return value.toLocaleString('en-US');
}

/** Every upload newest first, with its status, its counts and what was ignored in it. */
export function BatchList({ batches, count: total, page, onPageChange }: BatchListProps) {
  return (
    <Paper>
      <Table size="small" aria-label="Imports">
        <TableHead>
          <TableRow>
            <TableCell>File</TableCell>
            <TableCell>Uploaded</TableCell>
            <TableCell>Status</TableCell>
            <TableCell align="right">Rows</TableCell>
            <TableCell align="right">Valid</TableCell>
            <TableCell align="right">Warnings</TableCell>
            <TableCell align="right">Errors</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {batches.map((batch) => (
            <TableRow key={batch.id} hover>
              <TableCell sx={{ maxWidth: 360 }}>
                <Link component={RouterLink} to={`/imports/${batch.id}`} sx={{ fontWeight: 500 }}>
                  {batch.file_name}
                </Link>
                {batch.warnings.map((warning) => (
                  <Typography key={warning} variant="caption" component="p" color="text.secondary">
                    {warning}
                  </Typography>
                ))}
              </TableCell>
              <TableCell className="num">{formatDateTime(batch.uploaded_at)}</TableCell>
              <TableCell>
                <StatusChip status={batch.status} />
              </TableCell>
              <TableCell align="right" className="num">
                {count(batch.total_rows)}
              </TableCell>
              <TableCell align="right" className="num">
                {count(batch.valid_rows)}
              </TableCell>
              <TableCell align="right" className="num">
                {count(batch.warning_rows)}
              </TableCell>
              <TableCell align="right" className="num">
                {count(batch.error_rows)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {total > PAGE_SIZE ? (
        <TablePagination
          component="div"
          count={total}
          page={page - 1}
          rowsPerPage={PAGE_SIZE}
          rowsPerPageOptions={[PAGE_SIZE]}
          onPageChange={(_, next) => onPageChange(next + 1)}
        />
      ) : null}
    </Paper>
  );
}
