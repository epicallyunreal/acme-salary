import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import type { InsightPayloads } from '../../api/types';
import { plot } from './chartTheme';
import { CostBars } from './CostBars';
import { count, money, people, share, SMALL_GROUP } from './figures';
import { ChartNote, ChartTable, InsightCard } from './InsightCard';

type ByCountry = InsightPayloads['by-country'];

/** Question 2: total cost per country, its share labelled on each bar. */
export function ByCountryCard({
  query,
  actions,
}: {
  query: UseQueryResult<ByCountry>;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="Where does payroll go, by country?"
      what="the payroll by country"
      query={query}
      on={query.data?.to}
      actions={actions}
    >
      {query.data ? <CountryChart data={query.data} /> : null}
    </InsightCard>
  );
}

function CountryChart({ data }: { data: ByCountry }) {
  const { currency } = data;
  const bars = data.rows
    .filter((row) => row.total_cost !== null)
    .map((row) => ({
      name: row.country.name,
      cost: plot(row.total_cost) ?? 0,
      label: share(row.share_pct, row.headcount),
      lines: [
        people(row.headcount),
        `Total cost ${money(row.total_cost, currency, row.headcount)}`,
        `Median gross ${money(row.median_gross, currency, row.headcount)}`,
        `${share(row.share_pct, row.headcount)} of total cost`,
      ],
    }));
  const withheld = data.rows
    .filter((row) => row.headcount > 0 && row.total_cost === null)
    .map((row) => row.country.name);
  return (
    <>
      {bars.length ? <CostBars bars={bars} currency={currency} /> : null}
      {withheld.length ? (
        <ChartNote>
          Not shown, fewer than {SMALL_GROUP} people: {withheld.join(', ')}.
        </ChartNote>
      ) : null}
      <ChartTable
        caption="Payroll by country"
        head={['Country', 'Headcount', 'Total cost', 'Median gross', 'Share of total cost']}
        rows={data.rows.map((row) => [
          row.country.name,
          count(row.headcount),
          money(row.total_cost, currency, row.headcount),
          money(row.median_gross, currency, row.headcount),
          share(row.share_pct, row.headcount),
        ])}
      />
    </>
  );
}
