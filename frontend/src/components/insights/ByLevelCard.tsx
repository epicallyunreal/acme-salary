import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  CartesianGrid,
  ComposedChart,
  ErrorBar,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { InsightPayloads, LevelRow } from '../../api/types';
import { AXIS, compactTick, CURSOR, GRID, plot, SERIES, STILL } from './chartTheme';
import { count, money, SPREAD_GROUP } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

type ByLevel = InsightPayloads['by-level'];

/** Question 5: per level, the median as a dot on a bar from p25 to p75, with whiskers from p10
 * to p90. Never min or max, each of which is one person's pay (D59). */
export function ByLevelCard({
  query,
  actions,
}: {
  query: UseQueryResult<ByLevel>;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="What does each level pay?"
      what="the pay by level"
      query={query}
      actions={actions}
    >
      {query.data ? <LevelChart data={query.data} /> : null}
    </InsightCard>
  );
}

function figures(row: LevelRow, currency: string): string[] {
  return [row.p10, row.p25, row.median, row.p75, row.p90].map((value) =>
    money(value, currency, row.headcount, SPREAD_GROUP),
  );
}

/** ErrorBar draws from the dot minus the first figure to the dot plus the second. */
function around(median: number | null, low: string | null, high: string | null) {
  const from = plot(low);
  const to = plot(high);
  return median === null || from === null || to === null ? null : [median - from, to - median];
}

function LevelChart({ data }: { data: ByLevel }) {
  const { currency } = data;
  const rows = data.rows.map((row) => {
    const median = plot(row.median);
    return {
      row,
      label: `L${row.level}`,
      median,
      quartiles: around(median, row.p25, row.p75),
      deciles: around(median, row.p10, row.p90),
    };
  });
  const shown = rows.some((item) => item.median !== null);
  const withheld = data.rows
    .filter((row) => row.headcount > 0 && row.median === null)
    .map((row) => `L${row.level}`);
  return (
    <>
      {shown ? (
        <>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} {...GRID} />
              <XAxis dataKey="label" {...AXIS} />
              <YAxis tickFormatter={compactTick(currency)} width={72} {...AXIS} />
              <Tooltip
                cursor={CURSOR}
                content={({ active, payload }) => {
                  const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
                  if (!active || !item) return null;
                  const [p10, p25, median, p75, p90] = figures(item.row, currency);
                  return (
                    <ChartTooltip
                      title={`Level ${item.row.level}, ${count(item.row.headcount)} people`}
                      lines={[
                        `Median ${median}`,
                        `p25 to p75 ${p25} to ${p75}`,
                        `p10 to p90 ${p10} to ${p90}`,
                      ]}
                    />
                  );
                }}
              />
              <Scatter dataKey="median" fill={SERIES[0]} {...STILL}>
                <ErrorBar
                  dataKey="quartiles"
                  direction="y"
                  width={0}
                  stroke={SERIES[0]}
                  strokeWidth={8}
                  strokeOpacity={0.35}
                />
                <ErrorBar
                  dataKey="deciles"
                  direction="y"
                  width={10}
                  stroke={SERIES[0]}
                  strokeWidth={1.5}
                />
              </Scatter>
            </ComposedChart>
          </ResponsiveContainer>
          <ChartNote>Dot: median. Bar: p25 to p75. Whiskers: p10 to p90.</ChartNote>
        </>
      ) : null}
      {withheld.length ? (
        <ChartNote>
          Not shown, fewer than {SPREAD_GROUP} people: {withheld.join(', ')}.
        </ChartNote>
      ) : null}
      <ChartTable
        caption="Pay by level"
        head={['Level', 'Headcount', 'p10', 'p25', 'Median', 'p75', 'p90']}
        rows={data.rows.map((row) => [
          `Level ${row.level}`,
          count(row.headcount),
          ...figures(row, currency),
        ])}
      />
    </>
  );
}
