import {
  Box,
  Button,
  Checkbox,
  FormControl,
  InputLabel,
  ListItemText,
  MenuItem,
  OutlinedInput,
  Select,
  type SelectChangeEvent,
  TextField,
} from '@mui/material';
import { type ChangeEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { useCountries, useDepartments } from '../../api/meta';
import type { EmployeeStatus, ReportingCurrency } from '../../api/types';
import { EMPLOYEE_STATUSES, LEVELS } from '../../lib/constants';
import type { DirectoryFilters } from '../grid/serverModel';

export const SEARCH_DELAY_MS = 300;

interface FilterBarProps {
  filters: DirectoryFilters;
  onChange: (patch: Partial<DirectoryFilters>) => void;
  onReset: () => void;
  filtered: boolean;
}

/** A text field that reports its value on Enter, on blur, or after `delay` ms of quiet. */
export function CommitField({
  label,
  value,
  onCommit,
  delay,
  ...rest
}: {
  label: string;
  value: string;
  onCommit: (value: string) => void;
  delay?: number;
  type?: string;
  placeholder?: string;
  width?: number;
}) {
  const { width, ...fieldProps } = rest;
  const [draft, setDraft] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shown = draft ?? value;

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const commit = (next: string) => {
    if (timer.current) clearTimeout(timer.current);
    setDraft(null);
    if (next !== value) onCommit(next);
  };

  const onInput = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.value;
    setDraft(next);
    if (delay !== undefined) {
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => commit(next), delay);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      commit(shown);
    }
  };

  return (
    <TextField
      label={label}
      value={shown}
      onChange={onInput}
      onBlur={() => commit(shown)}
      onKeyDown={onKeyDown}
      slotProps={{ inputLabel: fieldProps.type === 'date' ? { shrink: true } : undefined }}
      sx={{ width: width ?? 160 }}
      {...fieldProps}
    />
  );
}

interface MultiSelectProps<T extends string | number> {
  label: string;
  value: T[];
  options: { value: T; label: string }[];
  onChange: (value: T[]) => void;
  width?: number;
}

function MultiSelect<T extends string | number>({
  label,
  value,
  options,
  onChange,
  width = 170,
}: MultiSelectProps<T>) {
  const id = `filter-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const names = new Map(options.map((option) => [option.value, option.label]));
  return (
    <FormControl sx={{ width }}>
      <InputLabel id={`${id}-label`}>{label}</InputLabel>
      <Select<T[]>
        labelId={`${id}-label`}
        id={id}
        multiple
        value={value}
        onChange={(event: SelectChangeEvent<T[]>) => {
          const next = event.target.value;
          onChange((typeof next === 'string' ? next.split(',') : next) as T[]);
        }}
        input={<OutlinedInput label={label} />}
        renderValue={(selected) =>
          selected.map((item) => names.get(item) ?? String(item)).join(', ')
        }
      >
        {options.map((option) => (
          <MenuItem key={String(option.value)} value={option.value}>
            <Checkbox size="small" checked={value.includes(option.value)} />
            <ListItemText primary={option.label} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

const STATUS_LABELS: Record<EmployeeStatus, string> = {
  active: 'Active',
  exited: 'Exited',
  upcoming: 'Upcoming',
};

/** The directory's filters (SPEC F4). Every control writes straight to the URL state. */
export function FilterBar({ filters, onChange, onReset, filtered }: FilterBarProps) {
  const countries = useCountries();
  const departments = useDepartments();
  const localAllowed = filters.country.length === 1;
  const grossCurrency = filters.currency === 'local' ? 'local' : filters.currency.toUpperCase();

  return (
    <Box
      component="section"
      aria-label="Filters"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center', mb: 4 }}
    >
      <CommitField
        label="Search"
        placeholder="Name, code or email"
        value={filters.search}
        onCommit={(search) => onChange({ search })}
        delay={SEARCH_DELAY_MS}
        width={240}
      />
      <MultiSelect
        label="Country"
        value={filters.country}
        options={(countries.data ?? []).map((country) => ({
          value: country.code,
          label: country.name,
        }))}
        onChange={(country) => onChange({ country })}
      />
      <MultiSelect
        label="Department"
        value={filters.department}
        options={(departments.data ?? []).map((department) => ({
          value: department.code,
          label: department.name,
        }))}
        onChange={(department) => onChange({ department })}
      />
      <CommitField
        label="Designation"
        placeholder="Title, any case"
        value={filters.designation.join(', ')}
        onCommit={(text) =>
          onChange({
            designation: text
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
          })
        }
        width={180}
      />
      <MultiSelect
        label="Level"
        value={filters.level}
        options={LEVELS.map((level) => ({ value: level, label: `L${level}` }))}
        onChange={(level) => onChange({ level })}
        width={110}
      />
      <FormControl sx={{ width: 130 }}>
        <InputLabel id="filter-status-label">Status</InputLabel>
        <Select
          labelId="filter-status-label"
          id="filter-status"
          value={filters.status}
          label="Status"
          displayEmpty
          onChange={(event) => onChange({ status: event.target.value as EmployeeStatus | '' })}
        >
          <MenuItem value="">Any</MenuItem>
          {EMPLOYEE_STATUSES.map((status) => (
            <MenuItem key={status} value={status}>
              {STATUS_LABELS[status]}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      <CommitField
        label={`Gross min (${grossCurrency})`}
        value={filters.gross_min}
        onCommit={(gross_min) => onChange({ gross_min })}
        type="number"
        width={150}
      />
      <CommitField
        label={`Gross max (${grossCurrency})`}
        value={filters.gross_max}
        onCommit={(gross_max) => onChange({ gross_max })}
        type="number"
        width={150}
      />
      <CommitField
        label="Joined after"
        value={filters.joined_after}
        onCommit={(joined_after) => onChange({ joined_after })}
        type="date"
      />
      <CommitField
        label="Joined before"
        value={filters.joined_before}
        onCommit={(joined_before) => onChange({ joined_before })}
        type="date"
      />
      <FormControl sx={{ width: 120 }}>
        <InputLabel id="filter-currency-label">Currency</InputLabel>
        <Select
          labelId="filter-currency-label"
          id="filter-currency"
          value={filters.currency}
          label="Currency"
          onChange={(event) => onChange({ currency: event.target.value as ReportingCurrency })}
        >
          <MenuItem value="usd">USD</MenuItem>
          <MenuItem value="eur">EUR</MenuItem>
          {localAllowed ? <MenuItem value="local">Local</MenuItem> : null}
        </Select>
      </FormControl>
      {filtered ? (
        <Button variant="text" onClick={onReset}>
          Clear filters
        </Button>
      ) : null}
    </Box>
  );
}
