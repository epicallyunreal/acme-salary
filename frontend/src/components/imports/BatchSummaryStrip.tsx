import { Box, Typography } from '@mui/material';

import type { ImportBatch } from '../../api/types';
import { formatCount } from './counts';

type CountField =
  'total_rows' | 'valid_rows' | 'warning_rows' | 'error_rows' | 'skipped_rows' | 'noop_rows';

const COUNTS: [string, CountField][] = [
  ['Total', 'total_rows'],
  ['Valid', 'valid_rows'],
  ['Warning', 'warning_rows'],
  ['Error', 'error_rows'],
  ['Skipped', 'skipped_rows'],
  ['No-op', 'noop_rows'],
];

/** The batch's counts as labelled figures (SPEC section 10). A no-op row is valid too. */
export function BatchSummaryStrip({ batch }: { batch: ImportBatch }) {
  return (
    <Box
      component="dl"
      aria-label="Batch summary"
      sx={{ display: 'flex', flexWrap: 'wrap', columnGap: 10, rowGap: 3, m: 0, mb: 5 }}
    >
      {COUNTS.map(([label, key]) => (
        <Box key={key}>
          <Typography component="dt" variant="caption">
            {label}
          </Typography>
          <Typography
            component="dd"
            className="num"
            sx={{ m: 0, fontSize: '1.375rem', fontWeight: 600, lineHeight: 1.3 }}
          >
            {formatCount(batch[key])}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
