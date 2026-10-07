import { zodResolver } from '@hookform/resolvers/zod';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { useForm } from 'react-hook-form';

import { useExitEmployee } from '../../api/employees';
import type { EmployeeDetail } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { applyServerErrors, type FormMessage } from './applyServerErrors';
import { ErrorSummary } from './ErrorSummary';
import { exitSchema, type ExitValues } from './schemas';

interface ExitDialogProps {
  employee: EmployeeDetail;
  open: boolean;
  onClose: () => void;
  onDone: (notice: string) => void;
}

/** Mark exited: one date, the last working day. The open record closes the day after. */
export function ExitDialog({ employee, open, onClose, onDone }: ExitDialogProps) {
  const exit = useExitEmployee(employee.id);
  const [serverMessages, setServerMessages] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors },
  } = useForm<ExitValues>({
    resolver: zodResolver(exitSchema),
    mode: 'onBlur',
    defaultValues: { last_date: '' },
  });
  const { ref: dateRef, ...dateField } = register('last_date');

  const close = () => {
    reset();
    setServerMessages([]);
    exit.reset();
    onClose();
  };

  const submit = handleSubmit((values) => {
    setServerMessages([]);
    exit.mutate(values, {
      onSuccess: () => {
        close();
        onDone(`${employee.full_name} marked exited, last day ${formatDate(values.last_date)}.`);
      },
      onError: (error) => {
        setServerMessages(applyServerErrors(error, setError, { fields: ['last_date'] }));
        setAttempt((n) => n + 1);
      },
    });
  });

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="xs">
      <form onSubmit={submit} noValidate>
        <DialogTitle>Mark {employee.full_name} exited</DialogTitle>
        <DialogContent>
          <ErrorSummary title="Not marked exited" messages={serverMessages} attempt={attempt} />
          <DialogContentText sx={{ mb: 4 }}>
            The pay record in force closes the day after. A date in the future schedules the exit.
          </DialogContentText>
          <TextField
            {...dateField}
            inputRef={dateRef}
            id="exit-last-date"
            label="Last working day"
            type="date"
            fullWidth
            required
            error={Boolean(errors.last_date)}
            helperText={errors.last_date?.message ?? ' '}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={close}>Keep employed</Button>
          <Button type="submit" variant="contained" loading={exit.isPending}>
            Mark exited
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
