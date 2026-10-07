import { zodResolver } from '@hookform/resolvers/zod';
import { Box, Button, LinearProgress, Paper, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import { FormProvider, type Path, useForm, useWatch } from 'react-hook-form';
import { Link, useNavigate } from 'react-router';

import { useCreateEmployee } from '../../api/employees';
import { useComponents, useCountries, useDepartments } from '../../api/meta';
import type { EmployeeCreateInput, Gender } from '../../api/types';
import { ErrorState } from '../layout/ErrorState';
import { applyServerErrors, type FormMessage } from './applyServerErrors';
import { ErrorSummary } from './ErrorSummary';
import { fieldProblems, savedNotice } from './feedback';
import { linesToSend } from './lines';
import { RecordLinesFields } from './RecordLinesFields';
import { employeeCreateSchema, type EmployeeCreateValues } from './schemas';

/** The form's fields in the order they appear, with the id the error summary links to. */
const FIELDS = [
  ['full_name', 'employee-full-name'],
  ['email', 'employee-email'],
  ['gender', 'employee-gender'],
  ['country_code', 'employee-country'],
  ['department', 'employee-department'],
  ['designation', 'employee-designation'],
  ['level', 'employee-level'],
  ['joining_date', 'employee-joining-date'],
  ['effective_from', 'employee-effective-from'],
  ['bonus_annual', 'employee-bonus'],
  ['note', 'employee-note'],
] as const;

const GENDERS: [Gender, string][] = [
  ['female', 'Female'],
  ['male', 'Male'],
  ['other', 'Other'],
  ['undisclosed', 'Undisclosed'],
];
const LEVELS = ['1', '2', '3', '4', '5', '6'];

const EMPTY: EmployeeCreateValues = {
  full_name: '',
  email: '',
  gender: '',
  department: '',
  designation: '',
  level: '',
  country_code: '',
  joining_date: '',
  effective_from: '',
  bonus_annual: '',
  note: '',
  lines: {},
};

const grid = {
  display: 'grid',
  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
  gap: 4,
} as const;

/** A new employee and their first pay record in one save (SPEC F3). The code is assigned by the
 * server; the components shown are the chosen country's. */
export function EmployeeForm() {
  const navigate = useNavigate();
  const create = useCreateEmployee();
  const countries = useCountries();
  const departments = useDepartments();
  const methods = useForm<EmployeeCreateValues>({
    resolver: zodResolver(employeeCreateSchema),
    mode: 'onBlur',
    shouldFocusError: false,
    defaultValues: EMPTY,
  });
  const {
    register,
    handleSubmit,
    setError,
    control,
    formState: { errors, submitCount },
  } = methods;
  const countryCode = useWatch({ control, name: 'country_code' });
  const components = useComponents(countryCode || undefined);
  const currency = countries.data?.find((country) => country.code === countryCode)?.currency_code;
  const codes = (components.data ?? []).map((component) => component.code);
  const [serverMessages, setServerMessages] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);

  const field = (name: (typeof FIELDS)[number][0], helper = ' ') => {
    const { ref, ...rest } = register(name);
    const inputId = FIELDS.find(([candidate]) => candidate === name)?.[1];
    return {
      ...rest,
      inputRef: ref,
      id: inputId,
      error: Boolean(errors[name]),
      helperText: errors[name]?.message ?? helper,
    };
  };
  const selectProps = { select: { native: true }, inputLabel: { shrink: true } } as const;

  const submit = handleSubmit(
    (values) => {
      const lines = linesToSend(components.data ?? [], values.lines);
      const body: EmployeeCreateInput = {
        full_name: values.full_name,
        email: values.email,
        gender: values.gender as Gender,
        department: values.department,
        designation: values.designation,
        level: Number(values.level),
        country_code: values.country_code,
        joining_date: values.joining_date,
        note: values.note,
        lines,
        ...(values.effective_from ? { effective_from: values.effective_from } : {}),
        ...(values.bonus_annual ? { bonus_annual: values.bonus_annual } : {}),
      };
      setServerMessages([]);
      create.mutate(body, {
        onSuccess: (employee) =>
          navigate(`/employees/${employee.id}`, {
            state: {
              notice: savedNotice(
                `${employee.full_name} added as ${employee.employee_code}.`,
                employee.warnings,
              ),
            },
          }),
        onError: (error) => {
          setServerMessages(
            applyServerErrors(error, setError, {
              fields: FIELDS.map(([name]) => name as Path<EmployeeCreateValues>),
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
    <FormProvider {...methods}>
      <Box component="form" noValidate onSubmit={submit} aria-label="New employee">
        <ErrorSummary
          title="The employee was not saved"
          fields={submitCount ? fieldProblems(errors, FIELDS, codes) : []}
          messages={serverMessages}
          attempt={attempt}
        />

        <Paper component="section" aria-labelledby="identity-heading" sx={{ p: 6, mb: 6 }}>
          <Typography id="identity-heading" variant="h3" component="h2" sx={{ mb: 4 }}>
            Identity
          </Typography>
          <Box sx={grid}>
            <TextField label="Full name" required autoComplete="off" {...field('full_name')} />
            <TextField label="Email" type="email" required {...field('email')} />
            <TextField label="Gender" select required slotProps={selectProps} {...field('gender')}>
              <option value="">Choose a gender</option>
              {GENDERS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </TextField>
            <TextField
              label="Country"
              select
              required
              slotProps={selectProps}
              {...field('country_code', 'Sets the currency and the pay components')}
            >
              <option value="">Choose a country</option>
              {countries.data?.map((country) => (
                <option key={country.code} value={country.code}>
                  {country.name} ({country.currency_code})
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
              <option value="">Choose a department</option>
              {departments.data?.map((department) => (
                <option key={department.code} value={department.code}>
                  {department.name}
                </option>
              ))}
            </TextField>
            <TextField label="Designation" required {...field('designation')} />
            <TextField label="Level" select required slotProps={selectProps} {...field('level')}>
              <option value="">Choose a level</option>
              {LEVELS.map((level) => (
                <option key={level} value={level}>
                  Level {level}
                </option>
              ))}
            </TextField>
            <TextField
              label="Joining date"
              type="date"
              required
              slotProps={{ inputLabel: { shrink: true } }}
              {...field('joining_date', 'The employee code is assigned on save')}
            />
          </Box>
        </Paper>

        <Paper component="section" aria-labelledby="record-heading" sx={{ p: 6, mb: 6 }}>
          <Typography id="record-heading" variant="h3" component="h2" sx={{ mb: 4 }}>
            First pay record
          </Typography>
          <Box sx={{ ...grid, mb: 4 }}>
            <TextField
              label="Effective from"
              type="date"
              slotProps={{ inputLabel: { shrink: true } }}
              {...field('effective_from', 'Leave blank to use the joining date')}
            />
            <TextField
              label={currency ? `Bonus per year (${currency})` : 'Bonus per year'}
              slotProps={{ htmlInput: { inputMode: 'decimal', className: 'num' } }}
              {...field('bonus_annual', 'Leave blank for none')}
            />
          </Box>
          {!countryCode || !currency ? (
            <Typography color="text.secondary" sx={{ mb: 4 }}>
              Choose a country to see its pay components.
            </Typography>
          ) : components.isError ? (
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
            {...field('note', 'Why this pay, for the history')}
          />
        </Paper>

        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
          <Button component={Link} to="/employees">
            Cancel
          </Button>
          <Button type="submit" variant="contained" loading={create.isPending}>
            Save employee
          </Button>
        </Box>
      </Box>
    </FormProvider>
  );
}
