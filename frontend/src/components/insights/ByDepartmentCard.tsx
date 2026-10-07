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

import type { InsightPayloads } from '../../api/types';
import { formatCompact, formatMoney } from '../../lib/money';
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
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

type ByDepartment = InsightPayloads['by-department'];

/** Question 3: total cost per department, the figure at the tip of each bar. */
export function ByDepartmentCard({ query }: { query: UseQueryResult<ByDepartment> }) {
  return (
    <InsightCard
      question="Which departments cost most and pay most?"
      what="the payroll by department"
      query={query}
    >
      {query.data ? <DepartmentChart data={query.data} /> : null}
    </InsightCard>
  );
}

function DepartmentChart({ data }: { data: ByDepartment }) {
  const { currency } = data;
  const rows = data.rows
    .filter((row) => row.headcount > 0)
    .map((row) => ({
      row,
      name: row.department.name,
      cost: plot(row.total_cost),
      tip: row.total_cost === null ? '' : formatCompact(row.total_cost, currency),
    }));
  const empty = data.rows.filter((row) => row.headcount === 0).map((row) => row.department.name);
  return (
    <>
      <ResponsiveContainer width="100%" height={rows.length * 36 + 32}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 80, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} {...GRID} />
          <XAxis type="number" tickFormatter={compactTick(currency)} {...AXIS} />
          <YAxis type="category" dataKey="name" width={130} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              const { row } = item;
              return (
                <ChartTooltip
                  title={item.name}
                  lines={[
                    `${row.headcount} people`,
                    `Total cost ${money(row.total_cost, currency, row.headcount)}`,
                    `Mean gross ${money(row.mean_gross, currency, row.headcount)}`,
                    `Median gross ${money(row.median_gross, currency, row.headcount)}`,
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
            <LabelList dataKey="tip" position="right" fill={tokens.inkSecondary} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {empty.length ? <ChartNote>Nobody in {empty.join(', ')}.</ChartNote> : null}
      <ChartTable
        caption="Payroll by department"
        head={['Department', 'Headcount', 'Total cost', 'Mean gross', 'Median gross']}
        rows={data.rows.map((row) => [
          row.department.name,
          row.headcount,
          row.total_cost === null ? '—' : formatMoney(row.total_cost, currency),
          money(row.mean_gross, currency, row.headcount),
          money(row.median_gross, currency, row.headcount),
        ])}
      />
    </>
  );
}
