import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  ListItemText,
  MenuItem,
  OutlinedInput,
  Select,
  type SelectChangeEvent,
  TextField,
} from '@mui/material';
import {
  type ChangeEvent,
  Fragment,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';

import type { FieldErrors } from '../../api/client';
import { useCountries, useDepartments } from '../../api/meta';
import type { DirectoryStatus, ReportingCurrency } from '../../api/types';
import { DIRECTORY_STATUSES, LEVELS } from '../../lib/constants';
import { isAbove } from '../../lib/money';
import type { DirectoryFilters } from '../grid/serverModel';
import { PeriodControl } from './PeriodControl';
import type { DashboardFilters } from './useDashboardFilters';

export const SEARCH_DELAY_MS = 300;

interface FilterBarProps {
  filters: DirectoryFilters;
  onChange: (patch: Partial<DirectoryFilters>) => void;
  onReset: () => void;
  filtered: boolean;
  /** A 400's messages by field, the API's own words (D76). */
  errors?: FieldErrors | null;
}

/** A text field that reports its value on Enter, on blur, or after `delay` ms of quiet. */
export function CommitField({
  label,
  value,
  onCommit,
  delay,
  error,
  helperText,
  invalid,
  describedBy,
  ...rest
}: {
  label: string;
  value: string;
  onCommit: (value: string) => void;
  delay?: number;
  /** Why the API refused this value, in its own words, shown under the field in place of the
   * helper text. */
  error?: string;
  helperText?: string;
  /** Marked wrong by a message shown elsewhere, the one with the id `describedBy`. */
  invalid?: boolean;
  describedBy?: string;
  type?: string;
  placeholder?: string;
  width?: number;
}) {
  const { width, ...fieldProps } = rest;
  // A draft belongs to the value it was typed over: when the value changes from outside, the
  // draft is dropped and so is its pending commit (D76).
  const [draft, setDraft] = useState<{ text: string; over: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shown = draft !== null && draft.over === value ? draft.text : value;

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [value],
  );

  const commit = (next: string) => {
    if (timer.current) clearTimeout(timer.current);
    setDraft(null);
    if (next !== value) onCommit(next);
  };

  const onInput = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.value;
    setDraft({ text: next, over: value });
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
      error={Boolean(error) || invalid}
      helperText={error ?? helperText}
      slotProps={{
        inputLabel: fieldProps.type === 'date' ? { shrink: true } : undefined,
        htmlInput: describedBy ? { 'aria-describedby': describedBy } : undefined,
      }}
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
  /** Why the API refused this value, in its own words, shown under the field (D76). */
  error?: string;
}

function sameItems<T>(a: T[], b: T[]): boolean {
  return a.length === b.length && a.every((item) => b.includes(item));
}

/** A multiple select that reports its value when its menu closes, so a selection changed in
 * several clicks is one filter change: India to Germany never passes through no country or two,
 * which would reset a local currency (DESIGN section 6). */
function MultiSelect<T extends string | number>({
  label,
  value,
  options,
  onChange,
  width = 170,
  error,
}: MultiSelectProps<T>) {
  const id = `filter-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const names = new Map(options.map((option) => [option.value, option.label]));
  const [draft, setDraft] = useState<T[] | null>(null);
  const shown = draft ?? value;
  return (
    <FormControl sx={{ width }} error={Boolean(error)}>
      <InputLabel id={`${id}-label`}>{label}</InputLabel>
      <Select<T[]>
        labelId={`${id}-label`}
        id={id}
        aria-describedby={error ? `${id}-error` : undefined}
        multiple
        value={shown}
        onOpen={() => setDraft(value)}
        onChange={(event: SelectChangeEvent<T[]>) => {
          const next = event.target.value;
          setDraft((typeof next === 'string' ? next.split(',') : next) as T[]);
        }}
        onClose={() => {
          if (draft !== null && !sameItems(draft, value)) onChange(draft);
          setDraft(null);
        }}
        input={<OutlinedInput label={label} />}
        renderValue={(selected) =>
          selected.map((item) => names.get(item) ?? String(item)).join(', ')
        }
      >
        {options.map((option) => (
          <MenuItem key={String(option.value)} value={option.value}>
            <Checkbox size="small" checked={shown.includes(option.value)} />
            <ListItemText primary={option.label} />
          </MenuItem>
        ))}
      </Select>
      {error ? <FormHelperText id={`${id}-error`}>{error}</FormHelperText> : null}
    </FormControl>
  );
}

interface CodeSelectProps {
  value: string[];
  onChange: (value: string[]) => void;
  error?: string;
}

export function CountrySelect({ value, onChange, error }: CodeSelectProps) {
  const countries = useCountries();
  return (
    <MultiSelect
      label="Country"
      value={value}
      options={(countries.data ?? []).map((country) => ({
        value: country.code,
        label: country.name,
      }))}
      onChange={onChange}
      error={error}
    />
  );
}

export function DepartmentSelect({ value, onChange, error }: CodeSelectProps) {
  const departments = useDepartments();
  return (
    <MultiSelect
      label="Department"
      value={value}
      options={(departments.data ?? []).map((department) => ({
        value: department.code,
        label: department.name,
      }))}
      onChange={onChange}
      error={error}
    />
  );
}

const STATUS_LABELS: Record<DirectoryStatus, string> = {
  active: 'Active',
  exited: 'Exited',
  upcoming: 'Upcoming',
  any: 'Any',
};

/** The directory's filters (SPEC F4). Every control writes straight to the URL state. */
export function FilterBar({ filters, onChange, onReset, filtered, errors }: FilterBarProps) {
  // Clear filters drops every draft in the bar, a value it leaves as it was included, so nothing
  // typed before it is sent after it (D76).
  const [clears, setClears] = useState(0);
  const localAllowed = filters.country.length === 1;
  const grossCurrency = filters.currency === 'local' ? 'local' : filters.currency.toUpperCase();
  const errorOn = (field: string) => errors?.[field]?.join(' ');
  // Said under the two fields, the grid left to show what the API answers (D76).
  const grossInverted =
    filters.gross_min !== '' &&
    filters.gross_max !== '' &&
    isAbove(filters.gross_min, filters.gross_max);
  const grossProblemId = useId();

  return (
    <Box
      component="section"
      aria-label="Filters"
      // A field with a line under it grows downwards, so the bar lines its fields up at the top.
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'flex-start', mb: 4 }}
    >
      <Fragment key={clears}>
        <CommitField
          label="Search"
          placeholder="Name, code or email"
          value={filters.search}
          onCommit={(search) => onChange({ search })}
          delay={SEARCH_DELAY_MS}
          error={errorOn('search')}
          width={240}
        />
        <CountrySelect
          value={filters.country}
          onChange={(country) => onChange({ country })}
          error={errorOn('country')}
        />
        <DepartmentSelect
          value={filters.department}
          onChange={(department) => onChange({ department })}
          error={errorOn('department')}
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
          error={errorOn('designation')}
          helperText="Commas between titles, Enter applies"
          width={240}
        />
        <MultiSelect
          label="Level"
          value={filters.level}
          options={LEVELS.map((level) => ({ value: level, label: `L${level}` }))}
          onChange={(level) => onChange({ level })}
          width={110}
        />
        <FormControl sx={{ width: 130 }}>
          {/* Active by default, with Any one click away (D64). The label stays above the value. */}
          <InputLabel id="filter-status-label" shrink>
            Status
          </InputLabel>
          <Select
            labelId="filter-status-label"
            id="filter-status"
            value={filters.status}
            label="Status"
            notched
            displayEmpty
            onChange={(event) => onChange({ status: event.target.value as DirectoryStatus })}
          >
            {DIRECTORY_STATUSES.map((status) => (
              <MenuItem key={status} value={status}>
                {STATUS_LABELS[status]}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Box>
          <Box sx={{ display: 'flex', gap: 3 }}>
            <CommitField
              label={`Gross min (${grossCurrency})`}
              value={filters.gross_min}
              onCommit={(gross_min) => onChange({ gross_min })}
              error={errorOn('gross_min')}
              invalid={grossInverted}
              describedBy={grossInverted ? grossProblemId : undefined}
              type="number"
              width={150}
            />
            <CommitField
              label={`Gross max (${grossCurrency})`}
              value={filters.gross_max}
              onCommit={(gross_max) => onChange({ gross_max })}
              error={errorOn('gross_max')}
              invalid={grossInverted}
              describedBy={grossInverted ? grossProblemId : undefined}
              type="number"
              width={150}
            />
          </Box>
          {grossInverted ? (
            <FormHelperText id={grossProblemId} error role="alert" sx={{ mx: '14px' }}>
              Gross min is above Gross max
            </FormHelperText>
          ) : null}
        </Box>
        <CommitField
          label="Joined after"
          value={filters.joined_after}
          onCommit={(joined_after) => onChange({ joined_after })}
          error={errorOn('joined_after')}
          type="date"
        />
        <CommitField
          label="Joined before"
          value={filters.joined_before}
          onCommit={(joined_before) => onChange({ joined_before })}
          error={errorOn('joined_before')}
          type="date"
        />
        <CurrencySelect
          value={filters.currency}
          localAllowed={localAllowed}
          onChange={(currency) => onChange({ currency })}
        />
      </Fragment>
      {filtered ? (
        <Button
          variant="text"
          // As tall as the small fields, so it lines up with them at the top.
          sx={{ minHeight: 40 }}
          onClick={() => {
            setClears((count) => count + 1);
            onReset();
          }}
        >
          Clear filters
        </Button>
      ) : null}
    </Box>
  );
}

interface CurrencySelectProps {
  value: ReportingCurrency;
  localAllowed: boolean;
  onChange: (currency: ReportingCurrency) => void;
}

/** USD and EUR always; `Local` only while exactly one country is selected (SPEC F4, F5). */
export function CurrencySelect({ value, localAllowed, onChange }: CurrencySelectProps) {
  return (
    <FormControl sx={{ width: 120 }}>
      <InputLabel id="filter-currency-label">Currency</InputLabel>
      <Select
        labelId="filter-currency-label"
        id="filter-currency"
        value={value}
        label="Currency"
        onChange={(event) => onChange(event.target.value as ReportingCurrency)}
      >
        <MenuItem value="usd">USD</MenuItem>
        <MenuItem value="eur">EUR</MenuItem>
        {localAllowed ? <MenuItem value="local">Local</MenuItem> : null}
      </Select>
    </FormControl>
  );
}

interface DashboardFilterBarProps {
  filters: DashboardFilters;
  onChange: (patch: Partial<DashboardFilters>) => void;
  onReset: () => void;
  filtered: boolean;
  /** Set at the bar's far end, after the filters, such as a link to Help (D75). */
  aside?: ReactNode;
}

/** The dashboard's filters (SPEC F5): country, department, reporting currency, whether the people
 * who have left count, and the period (D64). */
export function DashboardFilterBar({
  filters,
  onChange,
  onReset,
  filtered,
  aside,
}: DashboardFilterBarProps) {
  return (
    <Box
      component="section"
      aria-label="Filters"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center', mb: 3 }}
    >
      <CountrySelect value={filters.country} onChange={(country) => onChange({ country })} />
      <DepartmentSelect
        value={filters.department}
        onChange={(department) => onChange({ department })}
      />
      <CurrencySelect
        value={filters.currency}
        localAllowed={filters.country.length === 1}
        onChange={(currency) => onChange({ currency })}
      />
      <FormControlLabel
        control={
          <Checkbox
            checked={filters.include_exited}
            onChange={(event) => onChange({ include_exited: event.target.checked })}
          />
        }
        label="Include exited"
      />
      <PeriodControl filters={filters} onChange={onChange} />
      {filtered ? (
        <Button variant="text" onClick={onReset}>
          Clear filters
        </Button>
      ) : null}
      {aside ? <Box sx={{ ml: 'auto' }}>{aside}</Box> : null}
    </Box>
  );
}
