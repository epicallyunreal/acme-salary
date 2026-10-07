import {
  Box,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';

import { useAudit } from '../../api/audit';
import type { AuditEntry } from '../../api/types';
import { formatDate, formatDateTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { EmptyState } from '../layout/EmptyState';
import { ErrorState } from '../layout/ErrorState';

type Snapshot = Record<string, unknown>;

const IDENTITY_LABELS: [key: string, label: string][] = [
  ['full_name', 'Name'],
  ['email', 'Email'],
  ['gender', 'Gender'],
  ['department', 'Department'],
  ['designation', 'Designation'],
  ['level', 'Level'],
  ['joining_date', 'Joined'],
  ['last_date', 'Last day'],
];

function text(snapshot: Snapshot | null, key: string): string {
  const value = snapshot?.[key];
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

function shown(snapshot: Snapshot | null, key: string): string {
  const value = snapshot?.[key];
  if (value === null || value === undefined || value === '') return 'none';
  if (key === 'department' && typeof value === 'object') return text(value as Snapshot, 'name');
  if (key === 'joining_date' || key === 'last_date') return formatDate(String(value));
  return String(value);
}

function recordSummary(record: Snapshot | null): string {
  return `v${text(record, 'version')} from ${formatDate(text(record, 'effective_from'))}, gross ${formatMoney(
    text(record, 'gross_annual'),
    text(record, 'currency_code'),
  )}`;
}

/** What changed, in a sentence or a few: the entry's before and after are the API's shapes. */
function describeEntry({ action, before, after, import_batch }: AuditEntry): string[] {
  const via = import_batch ? ` by import ${import_batch}` : '';
  switch (action) {
    case 'create':
      return [`Created ${text(after, 'employee_code')}${via}`];
    case 'update': {
      const changes = IDENTITY_LABELS.filter(
        ([key]) => JSON.stringify(before?.[key]) !== JSON.stringify(after?.[key]),
      ).map(([key, label]) => `${label}: ${shown(before, key)} to ${shown(after, key)}`);
      return changes.length ? changes : [`Saved with no changes${via}`];
    }
    case 'exit':
      return [`Marked exited, last day ${formatDate(text(after, 'last_date'))}${via}`];
    case 'revise':
      return before
        ? [`Revision ${recordSummary(after)}${via}`]
        : [`First pay record ${recordSummary(after)}${via}`];
    case 'cancel':
      return [
        `Cancelled revision v${text(after, 'version')} from ${formatDate(text(after, 'effective_from'))}`,
      ];
    default:
      return [action.replace('_', ' ')];
  }
}

/** The employee page's audit list: who, when, what changed (SPEC F7). */
export function AuditList({ employeeId }: { employeeId: number }) {
  const audit = useAudit(employeeId);

  if (audit.isPending) return <LinearProgress aria-label="Loading the audit list" />;
  if (audit.isError) {
    return <ErrorState what="the audit list" onRetry={() => void audit.refetch()} />;
  }
  const { results, count } = audit.data;
  if (!results.length) return <EmptyState message="No changes recorded yet." />;

  return (
    <>
      <Table size="small" aria-label="Audit list">
        <TableHead>
          <TableRow>
            <TableCell>When</TableCell>
            <TableCell>Who</TableCell>
            <TableCell>What changed</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {results.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell sx={{ whiteSpace: 'nowrap' }} className="num">
                {formatDateTime(entry.timestamp)}
              </TableCell>
              <TableCell>{entry.actor ?? 'System'}</TableCell>
              <TableCell>
                {describeEntry(entry).map((line) => (
                  <Box key={line}>{line}</Box>
                ))}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {count > results.length ? (
        <Typography variant="caption" component="p" sx={{ mt: 3 }}>
          Showing the latest {results.length} of {count.toLocaleString('en-US')} changes.
        </Typography>
      ) : null}
    </>
  );
}
