import {
  Box,
  FormControl,
  FormHelperText,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from '@mui/material';
import { type ChangeEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';

import { PERIOD_FIRST, PERIOD_LAST } from '../../lib/constants';
import {
  type Period,
  PERIOD_LABELS,
  type PeriodName,
  periodProblem,
  PERIODS,
} from '../../lib/period';
import type { DashboardFilters } from './useDashboardFilters';

/** How long a date waits after its last change before it applies, so a date typed digit by digit
 * applies once and one picked from the calendar applies on its own. */
export const PERIOD_DELAY_MS = 600;

interface PeriodControlProps {
  filters: DashboardFilters;
  onChange: (patch: Partial<DashboardFilters>) => void;
}

/** The bar's period (SPEC F5, D64): a preset counted back from today, or Custom with From and To
 * beside it. */
export function PeriodControl({ filters, onChange }: PeriodControlProps) {
  const { period, from, to } = filters;
  return (
    <>
      <FormControl sx={{ width: 190 }}>
        <InputLabel id="filter-period-label">Period</InputLabel>
        <Select
          labelId="filter-period-label"
          id="filter-period"
          value={period}
          label="Period"
          onChange={(event) => {
            const next = event.target.value as PeriodName;
            // Custom starts from the dates on screen, so choosing it fetches nothing new.
            onChange(next === 'custom' ? { period: next, from, to } : { period: next });
          }}
        >
          {PERIODS.map((name) => (
            <MenuItem key={name} value={name}>
              {PERIOD_LABELS[name]}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {period === 'custom' ? (
        <CustomRange
          period={{ from, to }}
          onChange={(dates) => onChange({ period: 'custom', ...dates })}
        />
      ) : null}
    </>
  );
}

/** From and To. A range the API would refuse says why under the fields, keeps what was typed so
 * it can be put right, and leaves the dashboard on the last period that was valid (D64). */
function CustomRange({ period, onChange }: { period: Period; onChange: (period: Period) => void }) {
  const [draft, setDraft] = useState<Period | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const problemId = useId();
  const shown = draft ?? period;

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const apply = (next: Period) => {
    if (timer.current) clearTimeout(timer.current);
    const wrong = periodProblem(next);
    setProblem(wrong);
    if (wrong) return;
    setDraft(null);
    if (next.from !== period.from || next.to !== period.to) onChange(next);
  };

  const edit = (field: keyof Period) => (event: ChangeEvent<HTMLInputElement>) => {
    const next = { ...shown, [field]: event.target.value };
    setDraft(next);
    setProblem(null);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => apply(next), PERIOD_DELAY_MS);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      apply(shown);
    }
  };

  const dateField = (field: keyof Period, label: string) => (
    <TextField
      label={label}
      type="date"
      value={shown[field]}
      onChange={edit(field)}
      onBlur={() => {
        if (draft) apply(draft);
      }}
      onKeyDown={onKeyDown}
      error={problem !== null}
      slotProps={{
        inputLabel: { shrink: true },
        htmlInput: {
          min: PERIOD_FIRST,
          max: PERIOD_LAST,
          'aria-describedby': problem ? problemId : undefined,
        },
      }}
      sx={{ width: 160 }}
    />
  );

  return (
    <Box>
      <Box sx={{ display: 'flex', gap: 3 }}>
        {dateField('from', 'From')}
        {dateField('to', 'To')}
      </Box>
      {problem ? (
        <FormHelperText id={problemId} error role="alert">
          {problem}
        </FormHelperText>
      ) : null}
    </Box>
  );
}
