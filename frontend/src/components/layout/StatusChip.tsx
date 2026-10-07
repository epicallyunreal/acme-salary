import { Chip } from '@mui/material';

import type { StatusTone } from '../../lib/theme';

/** Every status the UI shows, mapped to one of the five tinted chips of DESIGN section 7. */
const TONES: Record<string, StatusTone> = {
  active: 'success',
  exited: 'neutral',
  upcoming: 'info',
  current: 'success',
  scheduled: 'info',
  ended: 'neutral',
  cancelled: 'neutral',
  valid: 'success',
  warning: 'warning',
  error: 'error',
  skipped: 'neutral',
  noop: 'neutral',
  create: 'info',
  update: 'info',
  revise: 'info',
  review: 'info',
  approved: 'success',
  failed: 'error',
  discarded: 'neutral',
};

interface StatusChipProps {
  status: string;
  label?: string;
}

/** A small chip with the status as text, never colour alone. */
export function StatusChip({ status, label }: StatusChipProps) {
  const tone = TONES[status] ?? 'neutral';
  return (
    <Chip
      size="small"
      label={label ?? status}
      sx={(theme) => ({
        color: theme.tokens.status[tone].text,
        bgcolor: theme.tokens.status[tone].fill,
        height: 22,
        fontSize: 12,
      })}
    />
  );
}
