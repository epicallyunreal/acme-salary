import VisibilityOffOutlinedIcon from '@mui/icons-material/VisibilityOffOutlined';
import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  InputAdornment,
  TextField,
} from '@mui/material';
import { useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useState } from 'react';

import { ApiError, type FieldErrors } from '../../api/client';
import { getResetCounts, useResetCounts, useResetDemo } from '../../api/demo';
import type { ResetCounts } from '../../api/types';
import { mayStillBeRunning, waitFor } from '../../lib/poll';
import type { FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { deletes } from './deletes';

/** Why a reset was refused, for the summary at the top of the dialog. The password and the
 * confirmation map onto their fields instead. */
function resetProblems(error: unknown): FormMessage[] {
  if (!(error instanceof ApiError)) {
    return [{ key: null, message: 'Nothing was sent. Check your connection and try again.' }];
  }
  if (error.status === 429) {
    return [{ key: null, message: 'Too many attempts. Wait an hour and try again.' }];
  }
  return [{ key: null, message: error.detail() ?? `Error ${error.status}` }];
}

const STILL_WORKING = 'Still working. The server is emptying the database.';
const GAVE_UP =
  'The server may still be working, or the reset was refused; reload the page and check the counts.';

/** After a reset the pay tables are empty, the audit log holding the reset's own entry. */
function emptied(counts: ResetCounts): boolean {
  return (
    counts.employees === 0 &&
    counts.compensation_records === 0 &&
    counts.compensation_lines === 0 &&
    counts.import_batches === 0 &&
    counts.import_rows === 0
  );
}

interface ResetDialogProps {
  open: boolean;
  onClose: () => void;
  onDone: (deleted: ResetCounts) => void;
}

/** The danger zone's dialog: the live counts, the password, the word RESET, and the button
 * disabled until both are filled (SPEC F9, D72). */
export function ResetDialog({ open, onClose, onDone }: ResetDialogProps) {
  const counts = useResetCounts(open);
  const reset = useResetDemo();
  const client = useQueryClient();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [shown, setShown] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const busy = reset.isPending || waiting;
  const ready = password.length > 0 && confirm.length > 0 && !busy;

  const done = (deleted: ResetCounts) => {
    setPassword('');
    setConfirm('');
    onDone(deleted);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setErrors({});
    setProblems([]);
    reset.mutate(
      { password, confirm },
      {
        onSuccess: done,
        onError: async (error) => {
          if (error instanceof ApiError && (error.status === 403 || error.status === 400)) {
            setAttempt((count) => count + 1);
            setErrors(error.fieldErrors());
            return;
          }
          if (!mayStillBeRunning(error)) {
            setAttempt((count) => count + 1);
            setProblems(resetProblems(error));
            return;
          }
          // The proxy cut the request, but the server empties on: the counts reach zero (D72).
          const before = counts.data;
          setWaiting(true);
          const now = await waitFor(async () => {
            const latest = await getResetCounts();
            return emptied(latest) ? latest : null;
          });
          setWaiting(false);
          if (now) {
            client.clear();
            done(before ?? now);
          } else {
            setAttempt((count) => count + 1);
            setProblems([{ key: null, message: GAVE_UP }]);
          }
        },
      },
    );
  };

  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="reset-title" fullWidth maxWidth="sm">
      <form onSubmit={submit} noValidate>
        <DialogTitle id="reset-title">Empty the database?</DialogTitle>
        <DialogContent>
          <ErrorSummary
            title="The database was not emptied"
            messages={problems}
            attempt={attempt}
          />
          <DialogContentText id="reset-description">
            {counts.data ? deletes(counts.data) : 'Counting what will be deleted.'}
          </DialogContentText>
          {waiting ? (
            <DialogContentText role="status" sx={{ mt: 2 }}>
              {STILL_WORKING}
            </DialogContentText>
          ) : null}
          <TextField
            id="reset-password"
            label="Your password"
            type={shown ? 'text' : 'password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            error={Boolean(errors.password)}
            helperText={errors.password?.[0]}
            fullWidth
            sx={{ mt: 4 }}
            slotProps={{
              input: {
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      aria-label={shown ? 'Hide password' : 'Show password'}
                      onClick={() => setShown((value) => !value)}
                      edge="end"
                    >
                      {shown ? <VisibilityOffOutlinedIcon /> : <VisibilityOutlinedIcon />}
                    </IconButton>
                  </InputAdornment>
                ),
              },
            }}
          />
          <TextField
            id="reset-confirm"
            label="Type RESET to confirm"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            autoComplete="off"
            error={Boolean(errors.confirm)}
            helperText={errors.confirm?.[0]}
            fullWidth
            sx={{ mt: 3 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" color="error" variant="contained" disabled={!ready} loading={busy}>
            Empty the database
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
