import type { UseQueryResult } from '@tanstack/react-query';

import type { InsightPayloads } from '../../api/types';
import { formatCompact } from '../../lib/money';
import { plot } from './chartTheme';
import { CostBars } from './CostBars';
import { count, money, people, SMALL_GROUP } from './figures';
import { ChartNote, ChartTable, InsightCard } from './InsightCard';

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
  const bars = data.rows
    .filter((row) => row.total_cost !== null)
    .map((row) => ({
      name: row.department.name,
      cost: plot(row.total_cost) ?? 0,
      label: row.total_cost === null ? '' : formatCompact(row.total_cost, currency),
      lines: [
        people(row.headcount),
        `Total cost ${money(row.total_cost, currency, row.headcount)}`,
        `Mean gross ${money(row.mean_gross, currency, row.headcount)}`,
        `Median gross ${money(row.median_gross, currency, row.headcount)}`,
      ],
    }));
  const withheld = data.rows
    .filter((row) => row.headcount > 0 && row.total_cost === null)
    .map((row) => row.department.name);
  const empty = data.rows.filter((row) => row.headcount === 0).map((row) => row.department.name);
  return (
    <>
      {bars.length ? <CostBars bars={bars} currency={currency} /> : null}
      {withheld.length ? (
        <ChartNote>
          Not shown, fewer than {SMALL_GROUP} people: {withheld.join(', ')}.
        </ChartNote>
      ) : null}
      {empty.length ? <ChartNote>Nobody in {empty.join(', ')}.</ChartNote> : null}
      <ChartTable
        caption="Payroll by department"
        head={['Department', 'Headcount', 'Total cost', 'Mean gross', 'Median gross']}
        rows={data.rows.map((row) => [
          row.department.name,
          count(row.headcount),
          money(row.total_cost, currency, row.headcount),
          money(row.mean_gross, currency, row.headcount),
          money(row.median_gross, currency, row.headcount),
        ])}
      />
    </>
  );
}
