import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@mui/material';
import { useState } from 'react';

import { useCancelRevision } from '../../api/compensation';
import type { CompensationRecord } from '../../api/types';
import { dayBefore, formatDate } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { visuallyHidden } from '../../lib/a11y';
import { applyServerErrors, type FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { type Notice, savedNotice } from '../forms/feedback';
import { EmptyState } from '../layout/EmptyState';
import { StatusChip } from '../layout/StatusChip';

type RecordState = 'cancelled' | 'scheduled' | 'current' | 'ended';

function stateOf(record: CompensationRecord): RecordState {
  if (record.cancelled_at) return 'cancelled';
  if (record.is_scheduled) return 'scheduled';
  if (record.is_current) return 'current';
  return 'ended';
}

/** The period a record covers, by its last day: `effective_to` is exclusive (SPEC section 4). */
function period(record: CompensationRecord, state: RecordState): string {
  const from = formatDate(record.effective_from);
  if (state === 'cancelled' || state === 'scheduled') return `from ${from}`;
  if (record.effective_to === null) return `${from} onwards`;
  return `${from} to ${formatDate(dayBefore(record.effective_to))}`;
}

interface HistoryListProps {
  records: CompensationRecord[];
  onCancel: (record: CompensationRecord) => void;
}

/** Every record newest first with version and note; cancelled rows stay, greyed and labelled,
 * and only a scheduled revision can be cancelled (SPEC F3, section 10). Version 1 never can
 * (D26), so a future joiner's first record offers no Cancel. */
export function HistoryList({ records, onCancel }: HistoryListProps) {
  if (!records.length) return <EmptyState message="No pay records yet." />;

  return (
    <Table size="small" aria-label="Pay history">
      <TableHead>
        <TableRow>
          <TableCell>Version</TableCell>
          <TableCell>Period</TableCell>
          <TableCell>Status</TableCell>
          <TableCell align="right">Gross per year</TableCell>
          <TableCell>Note</TableCell>
          <TableCell>
            <Box component="span" sx={visuallyHidden}>
              Actions
            </Box>
          </TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {records.map((record) => {
          const state = stateOf(record);
          const cancelled = state === 'cancelled';
          return (
            <TableRow
              key={record.id}
              data-state={state}
              sx={cancelled ? (theme) => ({ '& td': { color: theme.tokens.inkMuted } }) : undefined}
            >
              <TableCell className="num">v{record.version}</TableCell>
              <TableCell>{period(record, state)}</TableCell>
              <TableCell>
                <StatusChip status={state} />
              </TableCell>
              <TableCell
                align="right"
                className="num"
                sx={cancelled ? { textDecoration: 'line-through' } : undefined}
              >
                {formatMoney(record.gross_annual, record.currency_code)}
              </TableCell>
              <TableCell>
                {cancelled
                  ? `Cancelled ${formatDate(record.cancelled_at)}${record.cancelled_by ? ` by ${record.cancelled_by}` : ''}`
                  : record.note}
              </TableCell>
              <TableCell align="right">
                {state === 'scheduled' && record.version > 1 ? (
                  <Button
                    size="small"
                    onClick={() => onCancel(record)}
                    aria-label={`Cancel revision v${record.version}`}
                  >
                    Cancel
                  </Button>
                ) : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

interface CancelRevisionDialogProps {
  employeeId: number;
  record: CompensationRecord;
  onClose: () => void;
  onDone: (notice: Notice) => void;
}

/** Cancelling is a mark, not a delete, but it stops a raise, so it is confirmed first. */
export function CancelRevisionDialog({
  employeeId,
  record,
  onClose,
  onDone,
}: CancelRevisionDialogProps) {
  const cancel = useCancelRevision(employeeId);
  const [messages, setMessages] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);

  const confirm = () => {
    setMessages([]);
    cancel.mutate(record.id, {
      onSuccess: () => {
        onClose();
        onDone(savedNotice(`Revision v${record.version} cancelled.`));
      },
      onError: (error) => {
        setMessages(applyServerErrors(error, () => undefined, { fields: [] }));
        setAttempt((count) => count + 1);
      },
    });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Cancel revision v{record.version}?</DialogTitle>
      <DialogContent>
        <ErrorSummary title="Not cancelled" messages={messages} attempt={attempt} />
        <DialogContentText>
          The revision from {formatDate(record.effective_from)} will not take effect. It stays in
          the history, marked cancelled.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>
          Keep revision
        </Button>
        <Button color="error" variant="contained" onClick={confirm} loading={cancel.isPending}>
          Cancel revision
        </Button>
      </DialogActions>
    </Dialog>
  );
}
