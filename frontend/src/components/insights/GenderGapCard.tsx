import type { UseQueryResult } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  type LabelProps,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { GapRow, InsightPayloads } from '../../api/types';
import { tokens } from '../../lib/theme';
import {
  AXIS,
  BAR_GAP,
  BAR_SIZE,
  compactTick,
  CURSOR,
  GRID,
  plot,
  ROUND_TOP,
  SERIES,
  STILL,
} from './chartTheme';
import { count, money } from './figures';
import { ChartTable, ChartTooltip, InsightCard } from './InsightCard';

type GenderGap = InsightPayloads['gender-gap'];

const SERIES_LABEL: Record<string, string> = { female: 'Female', male: 'Male' };

function gap(row: GapRow): string {
  return row.gap_pct === null ? (row.reason ?? 'group too small') : `${row.gap_pct}%`;
}

/** Question 6: median gross of women and men per country and overall, the gap above each pair. */
export function GenderGapCard({ query }: { query: UseQueryResult<GenderGap> }) {
  return (
    <InsightCard question="Is there a gender pay gap?" what="the gender pay gap" query={query} wide>
      {query.data ? <GapChart data={query.data} /> : null}
    </InsightCard>
  );
}

/** The gap above its pair: the pair spans from the female bar to this male bar, so its middle
 * is half a gap to the left of this bar's left edge. */
function GapLabel({ x, value }: LabelProps) {
  return (
    <text
      x={Number(x) - BAR_GAP / 2}
      y={14}
      textAnchor="middle"
      fill={tokens.inkSecondary}
      fontSize={12}
      style={{ fontVariantNumeric: 'tabular-nums' }}
    >
      {value}
    </text>
  );
}

function GapChart({ data }: { data: GenderGap }) {
  const { currency } = data;
  const rows = data.rows
    .filter(
      (row) =>
        row.country === null || row.female.median_gross !== null || row.male.median_gross !== null,
    )
    .map((row) => ({
      row,
      label: row.country?.name ?? 'Overall',
      female: plot(row.female.median_gross),
      male: plot(row.male.median_gross),
      gap: gap(row),
    }));
  return (
    <>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} barGap={BAR_GAP} margin={{ top: 28, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} {...GRID} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis tickFormatter={compactTick(currency)} width={72} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              const { row } = item;
              return (
                <ChartTooltip
                  title={item.label}
                  lines={[
                    `Female: ${count(row.female.headcount)}, median ${money(row.female.median_gross, currency, row.female.headcount)}`,
                    `Male: ${count(row.male.headcount)}, median ${money(row.male.median_gross, currency, row.male.headcount)}`,
                    `Gap ${item.gap}`,
                  ]}
                />
              );
            }}
          />
          <Legend formatter={(value: string) => SERIES_LABEL[value] ?? value} />
          <Bar
            dataKey="female"
            fill={SERIES[0]}
            maxBarSize={BAR_SIZE}
            radius={ROUND_TOP}
            {...STILL}
          />
          <Bar dataKey="male" fill={SERIES[1]} maxBarSize={BAR_SIZE} radius={ROUND_TOP} {...STILL}>
            <LabelList dataKey="gap" content={GapLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartTable
        caption="Gender pay gap"
        head={[
          'Country',
          'Women',
          'Median, women',
          'Men',
          'Median, men',
          'Other',
          'Undisclosed',
          'Gap',
        ]}
        rows={data.rows.map((row) => [
          row.country?.name ?? 'Overall',
          count(row.female.headcount),
          money(row.female.median_gross, currency, row.female.headcount),
          count(row.male.headcount),
          money(row.male.median_gross, currency, row.male.headcount),
          count(row.other_count),
          count(row.undisclosed_count),
          gap(row),
        ])}
      />
    </>
  );
}
