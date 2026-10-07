import { zodResolver } from '@hookform/resolvers/zod';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  TextField,
} from '@mui/material';
import { useState } from 'react';
import { type Path, useForm } from 'react-hook-form';

import { useUpdateEmployee } from '../../api/employees';
import { useDepartments } from '../../api/meta';
import type { EmployeeDetail, IdentityPatch } from '../../api/types';
import { GENDER_LABELS, GENDERS, LEVELS } from '../../lib/constants';
import { applyServerErrors, type FormMessage } from './applyServerErrors';
import { ErrorSummary } from './ErrorSummary';
import { formPaper } from './formPaper';
import { fieldProblems, type Notice, savedNotice } from './feedback';
import { type IdentityFields, identitySchema, type IdentityValues } from './schemas';

const FIELDS = [
  ['full_name', 'edit-full-name'],
  ['email', 'edit-email'],
  ['gender', 'edit-gender'],
  ['department', 'edit-department'],
  ['designation', 'edit-designation'],
  ['level', 'edit-level'],
  ['joining_date', 'edit-joining-date'],
] as const;

function valuesOf(employee: EmployeeDetail): IdentityFields {
  return {
    full_name: employee.full_name,
    email: employee.email,
    gender: employee.gender,
    department: employee.department.code,
    designation: employee.designation,
    level: String(employee.level),
    joining_date: employee.joining_date,
  };
}

interface EditIdentityDialogProps {
  employee: EmployeeDetail;
  onClose: () => void;
  onDone: (notice: Notice) => void;
}

/** Edit who the employee is. Only the fields that changed are sent; the code and the country
 * cannot change (SPEC F3). Mounted only while open, so each opening starts from the employee. */
export function EditIdentityDialog({ employee, onClose, onDone }: EditIdentityDialogProps) {
  const update = useUpdateEmployee(employee.id);
  const departments = useDepartments();
  const [serverMessages, setServerMessages] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, dirtyFields, submitCount },
  } = useForm<IdentityFields, unknown, IdentityValues>({
    resolver: zodResolver(identitySchema),
    mode: 'onBlur',
    shouldFocusError: false,
    defaultValues: valuesOf(employee),
  });

  const field = (name: (typeof FIELDS)[number][0]) => {
    const { ref, ...rest } = register(name);
    return {
      ...rest,
      inputRef: ref,
      id: FIELDS.find(([candidate]) => candidate === name)?.[1],
      error: Boolean(errors[name]),
      helperText: errors[name]?.message ?? ' ',
    };
  };
  const selectProps = { select: { native: true }, inputLabel: { shrink: true } } as const;

  const submit = handleSubmit(
    (values) => {
      const patch: IdentityPatch = {};
      for (const [name] of FIELDS) {
        if (!dirtyFields[name]) continue;
        if (name === 'level') patch.level = Number(values.level);
        else if (name === 'gender') patch.gender = values.gender;
        else patch[name] = values[name];
      }
      if (!Object.keys(patch).length) {
        onClose();
        return;
      }
      setServerMessages([]);
      update.mutate(patch, {
        onSuccess: () => {
          onClose();
          onDone(savedNotice('Changes saved.'));
        },
        onError: (error) => {
          setServerMessages(
            applyServerErrors(error, setError, {
              fields: FIELDS.map(([name]) => name as Path<IdentityFields>),
            }),
          );
          setAttempt((count) => count + 1);
        },
      });
    },
    () => setAttempt((count) => count + 1),
  );

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" slotProps={{ paper: formPaper(submit) }}>
      <DialogTitle>Edit {employee.full_name}</DialogTitle>
      <DialogContent>
        <ErrorSummary
          title="The changes were not saved"
          fields={submitCount ? fieldProblems(errors, FIELDS) : []}
          messages={serverMessages}
          attempt={attempt}
        />
        <DialogContentText sx={{ mb: 4 }}>
          The employee code ({employee.employee_code}) and the country ({employee.country.name})
          cannot change.
        </DialogContentText>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 4 }}>
          <TextField label="Full name" required {...field('full_name')} />
          <TextField label="Email" type="email" required {...field('email')} />
          <TextField label="Gender" select required slotProps={selectProps} {...field('gender')}>
            {GENDERS.map((gender) => (
              <option key={gender} value={gender}>
                {GENDER_LABELS[gender]}
              </option>
            ))}
          </TextField>
          <TextField
            label="Department"
            select
            required
            slotProps={selectProps}
            {...field('department')}
          >
            {(departments.data ?? [employee.department]).map((department) => (
              <option key={department.code} value={department.code}>
                {department.name}
              </option>
            ))}
          </TextField>
          <TextField label="Designation" required {...field('designation')} />
          <TextField label="Level" select required slotProps={selectProps} {...field('level')}>
            {LEVELS.map((level) => (
              <option key={level} value={String(level)}>
                Level {level}
              </option>
            ))}
          </TextField>
          <TextField
            label="Joining date"
            type="date"
            required
            slotProps={{ inputLabel: { shrink: true } }}
            {...field('joining_date')}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Discard changes</Button>
        <Button type="submit" variant="contained" loading={update.isPending}>
          Save changes
        </Button>
      </DialogActions>
    </Dialog>
  );
}
