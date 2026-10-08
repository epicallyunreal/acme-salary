import { Box, Skeleton } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';

import type { SummaryInsight } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { formatAmount, formatCompactAmount, formatMoney } from '../../lib/money';
import { ErrorState } from '../layout/ErrorState';
import { SMALL_GROUP } from './figures';
import { KpiCard } from './KpiCard';

function counted(count: number, one: string, many: string): string {
  return `${formatAmount(String(count))} ${count === 1 ? one : many}`;
}

/** Question 1 (SPEC section 9) as five cards: headcount, annual cost, mean and median gross on the
 * period's last day, and what the period cost (D64). */
export function KpiRow({
  query,
  includeExited = false,
}: {
  query: UseQueryResult<SummaryInsight>;
  includeExited?: boolean;
}) {
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
        [0, 1, 2, 3, 4].map((slot) => (
          <Skeleton key={slot} variant="rounded" height={112} sx={{ flex: '1 1 200px' }} />
        ))
      ) : (
        <Figures summary={summary} includeExited={includeExited} />
      )}
    </Box>
  );
}

function Figures({ summary, includeExited }: { summary: SummaryInsight; includeExited: boolean }) {
  const { currency, headcount } = summary;
  // The API withholds every money figure for a population under five (D59).
  const withheld = headcount > 0 && summary.total_cost === null;
  const pay = (value: string | null) => (value === null ? '—' : formatAmount(value));
  const payCaption = withheld ? `Shown for ${SMALL_GROUP} people or more` : undefined;
  const on = `on ${formatDate(summary.to)}`;
  return (
    <>
      <KpiCard
        label={`Headcount ${on}`}
        figure={formatAmount(String(headcount))}
        caption={counted(summary.countries, 'country', 'countries')}
      />
      <KpiCard
        label={`Annual cost ${on}`}
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
        label={`Mean gross ${on}`}
        currency={currency}
        figure={pay(summary.mean_gross)}
        caption={payCaption}
      />
      <KpiCard
        label={`Median gross ${on}`}
        currency={currency}
        figure={pay(summary.median_gross)}
        caption={payCaption}
      />
      <Spent summary={summary} includeExited={includeExited} />
    </>
  );
}

/** What the period cost, captioned with its dates. It is withheld when any day of the period had 1
 * to 4 people (D68), and counts the people employed on each day, as trend does, so Include exited
 * does not apply to it either (D64). */
function Spent({ summary, includeExited }: { summary: SummaryInsight; includeExited: boolean }) {
  const { currency, spent } = summary;
  const withheld = spent.headcount > 0 && spent.total_cost === null;
  const caption = [
    `${formatDate(summary.from)} to ${formatDate(summary.to)}`,
    withheld ? `shown when each day has ${SMALL_GROUP} people or more` : null,
    includeExited ? "Include exited doesn't apply" : null,
  ]
    .filter(Boolean)
    .join(', ');
  return (
    <KpiCard
      label="Spent in period"
      currency={currency}
      figure={
        spent.total_cost !== null ? formatCompactAmount(spent.total_cost) : withheld ? '—' : '0'
      }
      exact={spent.total_cost === null ? undefined : formatMoney(spent.total_cost, currency)}
      caption={caption}
    />
  );
}
