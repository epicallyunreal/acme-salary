import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import type { ByTenureInsight } from '../../api/types';
import {
  AXIS,
  BAR_SIZE,
  compactTick,
  CURSOR,
  GRID,
  plot,
  ROUND_TOP,
  SERIES,
  STILL,
} from './chartTheme';
import { count, money, people, SMALL_GROUP } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

/** Question 9 (D62): median gross by completed years of service, within the level the card's
 * control picks, so tenure is compared within a level. */
export function ByTenureCard({
  query,
  actions,
}: {
  query: UseQueryResult<ByTenureInsight>;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="Does pay rise with tenure?"
      what="the pay by tenure"
      query={query}
      actions={actions}
    >
      {query.data ? <Tenure data={query.data} /> : null}
    </InsightCard>
  );
}

function Tenure({ data }: { data: ByTenureInsight }) {
  const { currency, rows } = data;
  const bars = rows.map((row) => ({ row, median: plot(row.median_gross) }));
  const withheld = rows
    .filter((row) => row.headcount > 0 && row.median_gross === null)
    .map((row) => row.label);
  return (
    <>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={bars} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} {...GRID} />
          <XAxis dataKey="row.label" {...AXIS} />
          <YAxis width={80} tickFormatter={compactTick(currency)} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof bars)[number] | undefined;
              if (!active || !item) return null;
              return (
                <ChartTooltip
                  title={item.row.label}
                  lines={[
                    people(item.row.headcount),
                    `median ${money(item.row.median_gross, currency, item.row.headcount)}`,
                  ]}
                />
              );
            }}
          />
          <Bar
            dataKey="median"
            fill={SERIES[0]}
            barSize={BAR_SIZE * 2}
            radius={ROUND_TOP}
            {...STILL}
          />
        </BarChart>
      </ResponsiveContainer>
      {withheld.length ? (
        <ChartNote>
          Not shown, fewer than {SMALL_GROUP} people: {withheld.join(', ')}.
        </ChartNote>
      ) : null}
      <ChartTable
        caption="Median gross by tenure"
        head={['Tenure', 'Headcount', 'Median gross']}
        rows={rows.map((row) => [
          row.label,
          count(row.headcount),
          money(row.median_gross, currency, row.headcount),
        ])}
      />
    </>
  );
}
