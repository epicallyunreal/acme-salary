import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';

import { ApiError } from '../../api/client';
import {
  afterApprove,
  getImport,
  refreshBatch,
  useApproveImport,
  useDiscardImport,
} from '../../api/imports';
import type { ImportBatch } from '../../api/types';
import type { FormMessage } from '../forms/applyServerErrors';
import { useBusy } from '../busy/busyContext';
import { appliedCounts, rowsWord } from './counts';

/** Why an approve or a discard was refused: the error count, the rows the re-check re-marked,
 * the failure that left the batch failed (SPEC F2), or the batch no longer in review. */
function batchActionProblems(error: unknown): FormMessage[] {
  if (!(error instanceof ApiError)) {
    return [{ key: null, message: 'Nothing was sent. Check your connection and try again.' }];
  }
  const data = (error.data ?? {}) as { rows?: number[]; error_summary?: string };
  const problems: FormMessage[] = [
    { key: null, message: error.detail() ?? `Error ${error.status}` },
  ];
  if (data.rows?.length) {
    const one = data.rows.length === 1;
    problems.push({
      key: null,
      message: `${one ? 'Row' : 'Rows'} ${data.rows.join(', ')} ${one ? 'is' : 'are'} marked with the reason. Skip ${one ? 'it' : 'them'} or upload the sheet again.`,
    });
  }
  if (data.error_summary) problems.push({ key: null, message: data.error_summary });
  return problems;
}

interface DialogProps {
  batch: ImportBatch;
  onClose: () => void;
  onDone: (notice: string) => void;
}

function applied(done: ImportBatch): string {
  return `Applied ${rowsWord(done.applied_rows)}: ${appliedCounts(done)}`;
}

const GAVE_UP =
  'The server may still be working, or the approve was refused; open the batch again.';
const DISCARD_GAVE_UP =
  'The server may still be working, or the discard was refused; open the batch again.';

/** The batch once it has left review, for a request the proxy cut (D72). */
function leftReview(id: number) {
  return async () => {
    const latest = await getImport(id);
    return latest.status === 'review' ? null : latest;
  };
}

export function ApproveDialog({ batch, onClose, onDone }: DialogProps) {
  const approve = useApproveImport(batch.id);
  const client = useQueryClient();
  const { run } = useBusy();

  // The confirmation closes and the busy dialog takes over until the server has answered, or,
  // the request cut, until the batch has left review. A batch that ended failed is a refusal.
  const confirm = async () => {
    onClose();
    const applying = batch.valid_rows + batch.warning_rows - batch.noop_rows;
    const result = await run(`Applying ${rowsWord(applying)}\u2026`, () => approve.mutateAsync(), {
      failedTitle: 'Nothing was applied',
      problems: batchActionProblems,
      gaveUp: GAVE_UP,
      recover: leftReview(batch.id),
      refusal: (done) =>
        done.status === 'approved'
          ? null
          : [
              { key: null, message: 'approve failed, the batch is marked failed' },
              ...(done.error_summary ? [{ key: null, message: done.error_summary }] : []),
            ],
    });
    if (!result.ok) {
      await refreshBatch(client, batch.id);
      return;
    }
    await afterApprove(client, result.value);
    onDone(applied(result.value));
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Approve {batch.file_name}?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Its valid and warning rows change the live records in one step, each change audited under
          this file. Skipped and unchanged rows are left out.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>
          Keep reviewing
        </Button>
        <Button variant="contained" onClick={() => void confirm()}>
          Approve and apply
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function DiscardDialog({ batch, onClose, onDone }: DialogProps) {
  const discard = useDiscardImport(batch.id);
  const client = useQueryClient();
  const { run } = useBusy();

  const confirm = async () => {
    onClose();
    const result = await run(`Discarding ${batch.file_name}\u2026`, () => discard.mutateAsync(), {
      failedTitle: 'Not discarded',
      problems: batchActionProblems,
      gaveUp: DISCARD_GAVE_UP,
      recover: leftReview(batch.id),
    });
    await refreshBatch(client, batch.id);
    if (result.ok) onDone(`${batch.file_name} discarded. Nothing in it was applied.`);
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Discard {batch.file_name}?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Nothing in it is applied. The batch and its rows stay listed for the record.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>
          Keep the batch
        </Button>
        <Button color="error" variant="contained" onClick={() => void confirm()}>
          Discard batch
        </Button>
      </DialogActions>
    </Dialog>
  );
}
