import type { UseQueryResult } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { CountryRow, InsightPayloads } from '../../api/types';
import { formatMoney } from '../../lib/money';
import { tokens } from '../../lib/theme';
import {
  AXIS,
  BAR_SIZE,
  compactTick,
  CURSOR,
  GRID,
  plot,
  ROUND_RIGHT,
  SERIES,
  STILL,
} from './chartTheme';
import { money } from './figures';
import { ChartTable, ChartTooltip, InsightCard } from './InsightCard';

type ByCountry = InsightPayloads['by-country'];

function share(row: CountryRow): string {
  return row.share_pct === null ? '—' : `${row.share_pct}%`;
}

/** Question 2: total cost per country, its share labelled on each bar. */
export function ByCountryCard({ query }: { query: UseQueryResult<ByCountry> }) {
  return (
    <InsightCard
      question="Where does payroll go, by country?"
      what="the payroll by country"
      query={query}
    >
      {query.data ? <CountryChart data={query.data} /> : null}
    </InsightCard>
  );
}

function CountryChart({ data }: { data: ByCountry }) {
  const { currency } = data;
  const rows = data.rows
    .filter((row) => row.headcount > 0)
    .map((row) => ({ row, name: row.country.name, cost: plot(row.total_cost), share: share(row) }));
  return (
    <>
      <ResponsiveContainer width="100%" height={rows.length * 36 + 32}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} {...GRID} />
          <XAxis type="number" tickFormatter={compactTick(currency)} {...AXIS} />
          <YAxis type="category" dataKey="name" width={120} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              return (
                <ChartTooltip
                  title={item.name}
                  lines={[
                    `${item.row.headcount} people`,
                    `Total cost ${money(item.row.total_cost, currency, item.row.headcount)}`,
                    `Median gross ${money(item.row.median_gross, currency, item.row.headcount)}`,
                    `${item.share} of total cost`,
                  ]}
                />
              );
            }}
          />
          <Bar
            dataKey="cost"
            fill={SERIES[0]}
            maxBarSize={BAR_SIZE}
            radius={ROUND_RIGHT}
            {...STILL}
          >
            <LabelList dataKey="share" position="right" fill={tokens.inkSecondary} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartTable
        caption="Payroll by country"
        head={['Country', 'Headcount', 'Total cost', 'Median gross', 'Share of total cost']}
        rows={data.rows.map((row) => [
          row.country.name,
          row.headcount,
          row.total_cost === null ? '—' : formatMoney(row.total_cost, currency),
          money(row.median_gross, currency, row.headcount),
          share(row),
        ])}
      />
    </>
  );
}
