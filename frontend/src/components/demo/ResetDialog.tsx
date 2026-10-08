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
import { type FormEvent, useState } from 'react';

import { ApiError, type FieldErrors } from '../../api/client';
import { useResetCounts, useResetDemo } from '../../api/demo';
import type { ResetCounts } from '../../api/types';
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
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [shown, setShown] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const ready = password.length > 0 && confirm.length > 0 && !reset.isPending;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setErrors({});
    setProblems([]);
    reset.mutate(
      { password, confirm },
      {
        onSuccess: (deleted) => {
          setPassword('');
          setConfirm('');
          onDone(deleted);
        },
        onError: (error) => {
          setAttempt((count) => count + 1);
          if (error instanceof ApiError && (error.status === 403 || error.status === 400)) {
            setErrors(error.fieldErrors());
          } else {
            setProblems(resetProblems(error));
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
          <Button
            type="submit"
            color="error"
            variant="contained"
            disabled={!ready}
            loading={reset.isPending}
          >
            Empty the database
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
