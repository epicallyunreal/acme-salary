import type { UseQueryResult } from '@tanstack/react-query';
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
import { money } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

type ByLevel = InsightPayloads['by-level'];

/** Question 5: per level, the median as a dot on a whisker from p25 to p75. */
export function ByLevelCard({ query }: { query: UseQueryResult<ByLevel> }) {
  return (
    <InsightCard question="What does each level pay?" what="the pay by level" query={query}>
      {query.data ? <LevelChart data={query.data} /> : null}
    </InsightCard>
  );
}

function figures(row: LevelRow, currency: string): string[] {
  return [row.min, row.p25, row.median, row.p75, row.max].map((value) =>
    money(value, currency, row.headcount),
  );
}

function LevelChart({ data }: { data: ByLevel }) {
  const { currency } = data;
  const rows = data.rows.map((row) => {
    const median = plot(row.median);
    return {
      row,
      label: `L${row.level}`,
      median,
      // ErrorBar draws from median minus the first figure to median plus the second.
      whisker: median === null ? null : [median - Number(row.p25), Number(row.p75) - median],
    };
  });
  const withheld = data.rows.filter((row) => row.median === null).map((row) => `L${row.level}`);
  return (
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
              const [min, p25, median, p75, max] = figures(item.row, currency);
              return (
                <ChartTooltip
                  title={`Level ${item.row.level}, ${item.row.headcount} people`}
                  lines={[
                    `Median ${median}`,
                    `p25 to p75 ${p25} to ${p75}`,
                    `Range ${min} to ${max}`,
                  ]}
                />
              );
            }}
          />
          <Scatter dataKey="median" fill={SERIES[0]} {...STILL}>
            <ErrorBar
              dataKey="whisker"
              direction="y"
              width={10}
              stroke={SERIES[0]}
              strokeWidth={2}
            />
          </Scatter>
        </ComposedChart>
      </ResponsiveContainer>
      {withheld.length ? (
        <ChartNote>Not shown, fewer than 5 people: {withheld.join(', ')}.</ChartNote>
      ) : null}
      <ChartTable
        caption="Pay by level"
        head={['Level', 'Headcount', 'Min', 'p25', 'Median', 'p75', 'Max']}
        rows={data.rows.map((row) => [
          `Level ${row.level}`,
          row.headcount,
          ...figures(row, currency),
        ])}
      />
    </>
  );
}
