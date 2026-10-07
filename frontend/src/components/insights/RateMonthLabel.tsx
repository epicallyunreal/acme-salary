import { Box, Tooltip, Typography } from '@mui/material';

import { useExchangeRates } from '../../api/meta';
import type { RateMonth } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { formatRate } from '../../lib/money';

/** "October 2026 rates" (SPEC F5), each pair's own rate and date on hover or focus (D28). */
export function RateMonthLabel({ rateMonth }: { rateMonth: RateMonth }) {
  const rates = useExchangeRates();
  const text = rateMonth.label.charAt(0).toUpperCase() + rateMonth.label.slice(1);
  const label = (
    <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
      {text}
    </Typography>
  );
  const pairs = rates.data?.rates ?? [];
  if (rateMonth.effective_from === null || !pairs.length) return <Box>{label}</Box>;
  return (
    <Box sx={{ display: 'inline-block' }}>
      <Tooltip
        // The label stays the name; the rates describe it.
        describeChild
        title={pairs.map((pair) => (
          <div key={`${pair.from_currency}-${pair.to_currency}`}>
            {pair.from_currency} to {pair.to_currency}: {formatRate(pair.rate)} from{' '}
            {formatDate(pair.effective_from)}
          </div>
        ))}
      >
        <Box component="span" tabIndex={0} sx={{ textDecoration: 'underline dotted' }}>
          {label}
        </Box>
      </Tooltip>
    </Box>
  );
}
