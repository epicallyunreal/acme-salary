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
import { useBusy } from '../busy/busyContext';
import type { FormMessage } from '../forms/applyServerErrors';
import { deletes } from './deletes';

/** The word the confirmation box must hold, exactly: no other case, no spaces around it. */
const CONFIRM_WORD = 'RESET';

/** Why a reset was refused, for the busy dialog: the two fields' messages, or the throttle's,
 * or the API's detail. A failure that is not an answer from the API is waited through (D72). */
function resetProblems(error: ApiError): FormMessage[] {
  if (error.status === 429) {
    return [{ key: null, message: 'Too many attempts. Wait an hour and try again.' }];
  }
  const fields = Object.values(error.fieldErrors()).flat();
  if (fields.length) return fields.map((message) => ({ key: null, message }));
  return [{ key: null, message: error.detail() ?? `Error ${error.status}` }];
}

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

/** The danger zone's dialog: the live counts, the password, the word RESET, and the button off
 * until the box holds exactly that word and the password field something (SPEC F9, D72). Once
 * pressed, the busy dialog takes over on top, so nothing here can be touched meanwhile. */
export function ResetDialog({ open, onClose, onDone }: ResetDialogProps) {
  const counts = useResetCounts(open);
  const reset = useResetDemo();
  const client = useQueryClient();
  const { busy, run } = useBusy();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [shown, setShown] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const ready = password.length > 0 && confirm === CONFIRM_WORD && busy === null;

  // Nothing typed outlives the dialog: a reopened one starts clean, the password hidden.
  const clear = () => {
    setPassword('');
    setConfirm('');
    setShown(false);
    setErrors({});
  };
  const close = () => {
    clear();
    onClose();
  };
  const done = (deleted: ResetCounts) => {
    clear();
    onDone(deleted);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setErrors({});
    // The proxy may cut the request while the server empties on: the counts reach zero (D72).
    const before = counts.data;
    const result = await run(
      'Emptying the database\u2026',
      () => reset.mutateAsync({ password, confirm }),
      {
        failedTitle: 'The database was not emptied',
        problems: resetProblems,
        gaveUp: GAVE_UP,
        recover: async () => {
          const latest = await getResetCounts();
          return emptied(latest) ? (before ?? latest) : null;
        },
      },
    );
    if (result.ok) {
      client.clear();
      done(result.value);
      return;
    }
    // The fields carry their refusal once the busy dialog is closed.
    const { error } = result;
    if (error instanceof ApiError && (error.status === 403 || error.status === 400)) {
      setErrors(error.fieldErrors());
    }
  };

  return (
    <Dialog open={open} onClose={close} aria-labelledby="reset-title" fullWidth maxWidth="sm">
      <form onSubmit={(event) => void submit(event)} noValidate>
        <DialogTitle id="reset-title">Empty the database?</DialogTitle>
        <DialogContent>
          <DialogContentText id="reset-description">
            {counts.data ? deletes(counts.data) : 'Counting what will be deleted.'}
          </DialogContentText>
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
          <Button onClick={close}>Cancel</Button>
          <Button type="submit" color="error" variant="contained" disabled={!ready}>
            Empty the database
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
