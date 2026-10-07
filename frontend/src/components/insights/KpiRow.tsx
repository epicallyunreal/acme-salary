import { Box, Skeleton } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';

import type { SummaryInsight } from '../../api/types';
import { formatAmount, formatCompactAmount, formatMoney } from '../../lib/money';
import { ErrorState } from '../layout/ErrorState';
import { SMALL_GROUP } from './figures';
import { KpiCard } from './KpiCard';

function counted(count: number, one: string, many: string): string {
  return `${formatAmount(String(count))} ${count === 1 ? one : many}`;
}

/** Question 1 (SPEC section 9) as four cards: headcount, total cost, mean and median gross. */
export function KpiRow({ query }: { query: UseQueryResult<SummaryInsight> }) {
  const summary = query.data;
  return (
    <Box
      component="section"
      aria-label="Key figures"
      sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, mb: 3 }}
    >
      {query.isError ? (
        <ErrorState what="the key figures" onRetry={() => void query.refetch()} />
      ) : !summary ? (
        [0, 1, 2, 3].map((slot) => (
          <Skeleton key={slot} variant="rounded" height={112} sx={{ flex: '1 1 200px' }} />
        ))
      ) : (
        <Figures summary={summary} />
      )}
    </Box>
  );
}

function Figures({ summary }: { summary: SummaryInsight }) {
  const { currency, headcount } = summary;
  // The API withholds every money figure for a population under five (D59).
  const withheld = headcount > 0 && summary.total_cost === null;
  const pay = (value: string | null) => (value === null ? '—' : formatAmount(value));
  const payCaption = withheld ? `Shown for ${SMALL_GROUP} people or more` : undefined;
  return (
    <>
      <KpiCard
        label="Headcount"
        figure={formatAmount(String(headcount))}
        caption={counted(summary.countries, 'country', 'countries')}
      />
      <KpiCard
        label="Total cost"
        currency={currency}
        figure={
          summary.total_cost !== null
            ? formatCompactAmount(summary.total_cost)
            : withheld
              ? '—'
              : '0'
        }
        exact={summary.total_cost === null ? undefined : formatMoney(summary.total_cost, currency)}
        caption={payCaption ?? counted(summary.departments, 'department', 'departments')}
      />
      <KpiCard
        label="Mean gross"
        currency={currency}
        figure={pay(summary.mean_gross)}
        caption={payCaption}
      />
      <KpiCard
        label="Median gross"
        currency={currency}
        figure={pay(summary.median_gross)}
        caption={payCaption}
      />
    </>
  );
}
