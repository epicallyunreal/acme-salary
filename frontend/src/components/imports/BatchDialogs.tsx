import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError } from '../../api/client';
import { afterApprove, getImport, useApproveImport, useDiscardImport } from '../../api/imports';
import type { ImportBatch } from '../../api/types';
import { mayStillBeRunning, waitFor } from '../../lib/poll';
import type { FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { rowsWord } from './counts';

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
  return (
    `Applied ${rowsWord(done.applied_rows)}: ${done.created_rows} created, ` +
    `${done.updated_rows} updated, ${done.revised_rows} revised.`
  );
}

const STILL_WORKING = 'Still working. The server is applying the rows.';
const GAVE_UP =
  'The server may still be working, or the approve was refused; open the batch again.';

export function ApproveDialog({ batch, onClose, onDone }: DialogProps) {
  const approve = useApproveImport(batch.id);
  const client = useQueryClient();
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [waiting, setWaiting] = useState(false);

  const refuse = (found: FormMessage[]) => {
    setProblems(found);
    setAttempt((n) => n + 1);
  };

  const confirm = () => {
    setProblems([]);
    approve.mutate(undefined, {
      onSuccess: (done) => {
        onClose();
        onDone(applied(done));
      },
      onError: async (error) => {
        if (!mayStillBeRunning(error)) {
          refuse(batchActionProblems(error));
          return;
        }
        // The proxy cut the request, but the server applies on: the batch leaves review (D72).
        setWaiting(true);
        const done = await waitFor(async () => {
          const latest = await getImport(batch.id);
          return latest.status === 'review' ? null : latest;
        });
        setWaiting(false);
        if (!done) {
          refuse([{ key: null, message: GAVE_UP }]);
          return;
        }
        await afterApprove(client, done);
        if (done.status === 'approved') {
          onClose();
          onDone(applied(done));
        } else {
          refuse([
            { key: null, message: 'approve failed, the batch is marked failed' },
            ...(done.error_summary ? [{ key: null, message: done.error_summary }] : []),
          ]);
        }
      },
    });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Approve {batch.file_name}?</DialogTitle>
      <DialogContent>
        <ErrorSummary title="Nothing was applied" messages={problems} attempt={attempt} />
        <DialogContentText>
          Its valid and warning rows change the live records in one step, each change audited under
          this file. Skipped and unchanged rows are left out.
        </DialogContentText>
        {waiting ? (
          <DialogContentText role="status" sx={{ mt: 2 }}>
            {STILL_WORKING}
          </DialogContentText>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>
          Keep reviewing
        </Button>
        <Button variant="contained" onClick={confirm} loading={approve.isPending || waiting}>
          Approve and apply
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function DiscardDialog({ batch, onClose, onDone }: DialogProps) {
  const discard = useDiscardImport(batch.id);
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);

  const confirm = () => {
    setProblems([]);
    discard.mutate(undefined, {
      onSuccess: () => {
        onClose();
        onDone(`${batch.file_name} discarded. Nothing in it was applied.`);
      },
      onError: (error) => {
        setProblems(batchActionProblems(error));
        setAttempt((n) => n + 1);
      },
    });
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Discard {batch.file_name}?</DialogTitle>
      <DialogContent>
        <ErrorSummary title="Not discarded" messages={problems} attempt={attempt} />
        <DialogContentText>
          Nothing in it is applied. The batch and its rows stay listed for the record.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>
          Keep the batch
        </Button>
        <Button color="error" variant="contained" onClick={confirm} loading={discard.isPending}>
          Discard batch
        </Button>
      </DialogActions>
    </Dialog>
  );
}
