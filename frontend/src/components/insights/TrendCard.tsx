import { Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { TrendInsight, TrendMeasure, TrendPoint } from '../../api/types';
import { formatAxisDate, formatDate } from '../../lib/dates';
import { AXIS, compactTick, GRID, plot, SERIES, STILL } from './chartTheme';
import { count, EMPLOYED_ON_EACH_DATE, money, people, SMALL_GROUP } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

/** Question 7 (D62, D64): total cost or headcount on the period's first day, on each month-end
 * between and on its last day, one line at a time and never two axes, every date at the one rate
 * in force on the last day. */
export function TrendCard({
  query,
  measure,
  includeExited,
  actions,
}: {
  query: UseQueryResult<TrendInsight>;
  measure: TrendMeasure;
  includeExited: boolean;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="How has total cost moved over the period?"
      what="the cost trend"
      query={query}
      actions={actions}
      wide
    >
      {query.data ? (
        <Trend data={query.data} measure={measure} includeExited={includeExited} />
      ) : null}
    </InsightCard>
  );
}

function Trend({
  data,
  measure,
  includeExited,
}: {
  data: TrendInsight;
  measure: TrendMeasure;
  includeExited: boolean;
}) {
  const { currency, points, rate_month: rateMonth } = data;
  const cost = measure === 'total_cost';
  const rows = points.map((point) => ({
    point,
    label: formatAxisDate(point.date),
    // A withheld total is null, so the line breaks there instead of dropping to zero.
    value: cost ? plot(point.total_cost) : point.headcount,
  }));
  const rates =
    rateMonth.effective_from === null ? `in ${rateMonth.label}` : `at ${rateMonth.label}`;
  const gaps = cost && points.some((point) => point.headcount > 0 && point.total_cost === null);
  return (
    <>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
        From {formatDate(data.from)} to {formatDate(data.to)}, {rates}.
      </Typography>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} {...GRID} />
          <XAxis dataKey="label" interval="preserveStartEnd" minTickGap={24} {...AXIS} />
          <YAxis
            width={cost ? 80 : 40}
            allowDecimals={false}
            tickFormatter={cost ? compactTick(currency) : undefined}
            {...AXIS}
          />
          <Tooltip
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              return (
                <ChartTooltip
                  title={formatDate(item.point.date)}
                  lines={lines(item.point, currency)}
                />
              );
            }}
          />
          <Line
            type="linear"
            dataKey="value"
            stroke={SERIES[0]}
            strokeWidth={2}
            dot={{ r: 2, fill: SERIES[0] }}
            {...STILL}
          />
        </LineChart>
      </ResponsiveContainer>
      {gaps ? (
        <ChartNote>
          A gap is a date with fewer than {SMALL_GROUP} people, where total cost is not shown.
        </ChartNote>
      ) : null}
      {includeExited ? <ChartNote>{EMPLOYED_ON_EACH_DATE}</ChartNote> : null}
      <ChartTable
        caption="Cost trend by date"
        head={['Date', 'Headcount', 'Total cost']}
        rows={points.map((point) => [
          formatDate(point.date),
          count(point.headcount),
          money(point.total_cost, currency, point.headcount),
        ])}
      />
    </>
  );
}

function lines(point: TrendPoint, currency: string): string[] {
  return [people(point.headcount), money(point.total_cost, currency, point.headcount)];
}
