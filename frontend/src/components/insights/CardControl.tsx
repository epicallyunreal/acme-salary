import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import { useId } from 'react';

interface CardControlProps<T extends string> {
  /** The group's accessible name, `Trend measure`. */
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}

/** A card's one control (D62): what it measures or how it slices, never who is counted. One
 * choice is always on, so clicking the chosen one again changes nothing. */
export function CardControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: CardControlProps<T>) {
  return (
    <ToggleButtonGroup
      size="small"
      exclusive
      value={value}
      aria-label={label}
      onChange={(_, next: T | null) => {
        if (next !== null) onChange(next);
      }}
      sx={{ flexShrink: 0 }}
    >
      {options.map((option) => (
        <ToggleButton key={option.value} value={option.value} sx={{ px: 1.5, py: 0.25 }}>
          {option.label}
        </ToggleButton>
      ))}
    </ToggleButtonGroup>
  );
}

/** The same control as a small select, for a choice too long for buttons: the Level. */
export function CardSelect<T extends string>({
  label,
  value,
  options,
  onChange,
}: CardControlProps<T>) {
  const labelId = useId();
  return (
    <FormControl size="small" sx={{ minWidth: 96, flexShrink: 0 }}>
      <InputLabel id={labelId}>{label}</InputLabel>
      <Select
        labelId={labelId}
        value={value}
        label={label}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <MenuItem key={option.value} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
