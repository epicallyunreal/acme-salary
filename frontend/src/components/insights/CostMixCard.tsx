import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { CostMixInsight, MixRow, MixView } from '../../api/types';
import { AXIS, BAR_SIZE, CURSOR, GRID, MIX_COLORS, MIX_OTHER, STILL } from './chartTheme';
import { count } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

const WHOLE: Record<MixView, string> = { cost: 'total cost', take_home: 'gross pay' };

/** Question 10 (D62): one bar per country stacked to 100%, as shares of total cost or of gross
 * pay split into net and each deduction, as the card's control picks. */
export function CostMixCard({
  query,
  actions,
}: {
  query: UseQueryResult<CostMixInsight>;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="What is pay made of?"
      what="the cost mix"
      query={query}
      actions={actions}
    >
      {query.data ? <Mix data={query.data} /> : null}
    </InsightCard>
  );
}

function shares(row: MixRow): string {
  return (row.segments ?? []).map((segment) => `${segment.name} ${segment.share_pct}%`).join(', ');
}

function Mix({ data }: { data: CostMixInsight }) {
  const shown = data.rows.filter((row) => row.segments !== null);
  const withheld = data.rows.filter((row) => row.headcount > 0 && row.segments === null);
  const bars = shown.map((row) => ({
    row,
    name: row.country.name,
    ...Object.fromEntries((row.segments ?? []).map((s) => [s.code, Number(s.share_pct)])),
  }));
  return (
    <>
      {shown.length ? (
        <ResponsiveContainer width="100%" height={Math.max(120, shown.length * 44 + 64)}>
          <BarChart
            data={bars}
            layout="vertical"
            stackOffset="expand"
            margin={{ top: 0, right: 16, bottom: 0, left: 0 }}
          >
            <CartesianGrid horizontal={false} {...GRID} />
            <XAxis
              type="number"
              tickFormatter={(value: number) => `${Math.round(value * 100)}%`}
              {...AXIS}
            />
            <YAxis type="category" dataKey="name" width={110} {...AXIS} />
            <Tooltip
              cursor={CURSOR}
              content={({ active, payload }) => {
                const item = payload?.[0]?.payload as (typeof bars)[number] | undefined;
                if (!active || !item) return null;
                return (
                  <ChartTooltip
                    title={item.row.country.name}
                    lines={(item.row.segments ?? []).map((s) => `${s.name}: ${s.share_pct}%`)}
                  />
                );
              }}
            />
            <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} />
            {/* One stacked bar per segment, in the one order the API gives them (D62). */}
            {data.segments.map(({ code, name }) => (
              <Bar
                key={code}
                dataKey={code}
                name={name}
                stackId="mix"
                maxBarSize={BAR_SIZE}
                fill={MIX_COLORS[code] ?? MIX_OTHER}
                {...STILL}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      ) : null}
      {withheld.length ? (
        <ChartNote>
          Not shown: {withheld.map((row) => `${row.country.name}, ${row.reason}`).join('; ')}.
        </ChartNote>
      ) : null}
      <ChartTable
        caption={`Shares of ${WHOLE[data.view]} by country`}
        head={['Country', 'Headcount', 'Shares']}
        rows={data.rows.map((row) => [
          row.country.name,
          count(row.headcount),
          row.segments ? shares(row) : (row.reason ?? '—'),
        ])}
      />
    </>
  );
}
