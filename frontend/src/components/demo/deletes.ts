import type { ResetCounts } from '../../api/types';
import { formatAmount } from '../../lib/money';

function counted(count: number, one: string, many: string): string {
  return `${formatAmount(String(count))} ${count === 1 ? one : many}`;
}

/** What a reset deletes, in words: the live counts the dialog shows (SPEC F9). */
export function deletes(counts: ResetCounts): string {
  return (
    `This deletes ${counted(counts.employees, 'employee', 'employees')}, ` +
    `${counted(counts.compensation_records, 'compensation record', 'compensation records')}, ` +
    `${counted(counts.compensation_lines, 'line', 'lines')}, ` +
    `${counted(counts.import_batches, 'import batch', 'import batches')} with ` +
    `${counted(counts.import_rows, 'row', 'rows')} and ` +
    `${counted(counts.audit_entries, 'audit entry', 'audit entries')}. ` +
    'Lookups, exchange rates and your login stay.'
  );
}
