import { zodResolver } from '@hookform/resolvers/zod';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  LinearProgress,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { FormProvider, type Path, useForm } from 'react-hook-form';

import { useReviseCompensation } from '../../api/compensation';
import { useComponents } from '../../api/meta';
import type { CompensationRecord, EmployeeDetail, RevisionInput } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { ErrorState } from '../layout/ErrorState';
import { applyServerErrors, type FormMessage } from './applyServerErrors';
import { ErrorSummary } from './ErrorSummary';
import { fieldProblems, type Notice, savedNotice } from './feedback';
import { amountsOf, linesToSend } from './lines';
import { RecordLinesFields } from './RecordLinesFields';
import { revisionSchema, type RevisionValues } from './schemas';

const FIELDS = [
  ['effective_from', 'revision-effective-from'],
  ['bonus_annual', 'revision-bonus'],
  ['note', 'revision-note'],
] as const;

function valuesFrom(latest: CompensationRecord | null): RevisionValues {
  return {
    effective_from: '',
    bonus_annual: latest?.bonus_annual ?? '',
    note: '',
    lines: amountsOf(latest),
  };
}

interface RevisionDialogProps {
  employee: EmployeeDetail;
  /** The latest live record: the new one must start after it, and starts from its amounts. */
  latest: CompensationRecord | null;
  onClose: () => void;
  onDone: (notice: Notice) => void;
}

/** A new revision: a date, the amounts and a note. A date after today schedules it (SPEC F3).
 * Mounted only while open, so each opening starts from the latest record. */
export function RevisionDialog({ employee, latest, onClose, onDone }: RevisionDialogProps) {
  const revise = useReviseCompensation(employee.id);
  const components = useComponents(employee.country.code);
  const currency = employee.country.currency_code;
  const codes = (components.data ?? []).map((component) => component.code);
  const [serverMessages, setServerMessages] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const methods = useForm<RevisionValues>({
    resolver: zodResolver(revisionSchema),
    mode: 'onBlur',
    shouldFocusError: false,
    defaultValues: valuesFrom(latest),
  });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, submitCount },
  } = methods;

  const field = (name: (typeof FIELDS)[number][0], helper = ' ') => {
    const { ref, ...rest } = register(name);
    return {
      ...rest,
      inputRef: ref,
      id: FIELDS.find(([candidate]) => candidate === name)?.[1],
      error: Boolean(errors[name]),
      helperText: errors[name]?.message ?? helper,
    };
  };

  const submit = handleSubmit(
    (values) => {
      const lines = linesToSend(components.data ?? [], values.lines);
      const body: RevisionInput = {
        effective_from: values.effective_from,
        note: values.note,
        lines,
        ...(values.bonus_annual ? { bonus_annual: values.bonus_annual } : {}),
      };
      setServerMessages([]);
      revise.mutate(body, {
        onSuccess: (record) => {
          onClose();
          onDone(savedNotice(`Revision v${record.version} saved.`, record.warnings));
        },
        onError: (error) => {
          setServerMessages(
            applyServerErrors(error, setError, {
              fields: FIELDS.map(([name]) => name as Path<RevisionValues>),
              componentCodes: codes,
              sentLineCodes: lines.map((line) => line.component),
            }),
          );
          setAttempt((count) => count + 1);
        },
      });
    },
    () => setAttempt((count) => count + 1),
  );

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <FormProvider {...methods}>
        <form onSubmit={submit} noValidate>
          <DialogTitle>Add a revision for {employee.full_name}</DialogTitle>
          <DialogContent>
            <ErrorSummary
              title="The revision was not saved"
              fields={submitCount ? fieldProblems(errors, FIELDS, codes) : []}
              messages={serverMessages}
              attempt={attempt}
            />
            <DialogContentText sx={{ mb: 4 }}>
              The amounts start from the latest record. A date after today schedules the revision;
              it can be cancelled until it takes effect.
            </DialogContentText>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
                gap: 4,
                mb: 4,
              }}
            >
              <TextField
                label="Effective from"
                type="date"
                required
                slotProps={{ inputLabel: { shrink: true } }}
                {...field(
                  'effective_from',
                  latest ? `After ${formatDate(latest.effective_from)}` : ' ',
                )}
              />
              <TextField
                label={`Bonus per year (${currency})`}
                slotProps={{ htmlInput: { inputMode: 'decimal', className: 'num' } }}
                {...field('bonus_annual', 'Leave blank for none')}
              />
            </Box>
            {components.isError ? (
              <ErrorState what="the pay components" onRetry={() => void components.refetch()} />
            ) : components.isPending ? (
              <LinearProgress aria-label="Loading the pay components" />
            ) : (
              <RecordLinesFields components={components.data} currency={currency} />
            )}
            <TextField
              label="Note"
              multiline
              minRows={2}
              fullWidth
              sx={{ mt: 4 }}
              {...field('note', 'The reason, for the history')}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Discard revision</Button>
            <Button type="submit" variant="contained" loading={revise.isPending}>
              Save revision
            </Button>
          </DialogActions>
        </form>
      </FormProvider>
    </Dialog>
  );
}
