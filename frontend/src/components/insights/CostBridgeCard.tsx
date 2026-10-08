import { Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { BridgePart, BridgePartName, CostBridgeInsight } from '../../api/types';
import { formatDate } from '../../lib/dates';
import { formatCompact, formatMoney } from '../../lib/money';
import { AXIS, BAR_SIZE, compactTick, CURSOR, GRID, plot, SERIES, STILL } from './chartTheme';
import { count, EMPLOYED_ON_EACH_DATE, people, SMALL_GROUP } from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

const LABELS: Record<BridgePartName, string> = {
  start: 'Start',
  leavers: 'Leavers',
  joiners: 'Joiners',
  pay_changes: 'Pay changes',
  end: 'End',
};
const TOTALS: readonly BridgePartName[] = ['start', 'end'];

/** Question 8 (D62, D64): start, minus leavers, plus joiners, plus pay changes, end, from the
 * period's first day to its last, both at the one rate in force on the last day. */
export function CostBridgeCard({
  query,
  includeExited,
  actions,
}: {
  query: UseQueryResult<CostBridgeInsight>;
  includeExited: boolean;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="Why did total cost move over the period?"
      what="the cost bridge"
      query={query}
      actions={actions}
    >
      {query.data ? <Bridge data={query.data} includeExited={includeExited} /> : null}
    </InsightCard>
  );
}

/** A figure for the table and the labels: the amount, a change with its sign, or why it is
 * withheld. */
function amountText(part: BridgePart, currency: string): string {
  if (part.amount === null) return part.reason ?? '';
  return formatMoney(part.amount, currency, { signed: !TOTALS.includes(part.part) });
}

interface BridgeBar {
  part: BridgePart;
  label: string;
  /** From the running total before the part to the one after, or `null` with no bar. */
  range: [number, number] | null;
  text: string;
}

/** Each change floats from the running total before it to the one after, start and end stand on
 * zero, and a withheld part has no bar. */
function bars(parts: BridgePart[], currency: string): BridgeBar[] {
  const rows: BridgeBar[] = [];
  let running = 0;
  for (const part of parts) {
    const value = plot(part.amount);
    let range: [number, number] | null = null;
    if (value !== null) {
      if (TOTALS.includes(part.part)) {
        range = [0, value];
        running = value;
      } else {
        range = [Math.min(running, running + value), Math.max(running, running + value)];
        running += value;
      }
    }
    rows.push({
      part,
      label: LABELS[part.part],
      range,
      text: part.amount === null ? '' : formatCompact(part.amount, currency),
    });
  }
  return rows;
}

function Bridge({ data, includeExited }: { data: CostBridgeInsight; includeExited: boolean }) {
  const { currency, parts, rate_month: rateMonth } = data;
  const rows = bars(parts, currency);
  const rates =
    rateMonth.effective_from === null ? `in ${rateMonth.label}` : `at ${rateMonth.label}`;
  const withheld = parts.some((part) => !TOTALS.includes(part.part) && part.amount === null);
  return (
    <>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
        From {formatDate(data.from)} to {formatDate(data.to)}, {rates}.
      </Typography>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={rows} margin={{ top: 24, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} {...GRID} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis width={80} tickFormatter={compactTick(currency)} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              return (
                <ChartTooltip
                  title={item.label}
                  lines={[people(item.part.people), amountText(item.part, currency)]}
                />
              );
            }}
          />
          <Bar dataKey="range" maxBarSize={BAR_SIZE} {...STILL}>
            {rows.map((row) => (
              <Cell
                key={row.part.part}
                fill={TOTALS.includes(row.part.part) ? SERIES[0] : SERIES[1]}
              />
            ))}
            <LabelList dataKey="text" position="top" style={AXIS.tick} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {withheld ? (
        <ChartNote>
          Leavers, joiners and pay changes are shown when none of them has 1 to {SMALL_GROUP - 1}{' '}
          people, since any one could be worked out from the others.
        </ChartNote>
      ) : null}
      {includeExited ? <ChartNote>{EMPLOYED_ON_EACH_DATE}</ChartNote> : null}
      <ChartTable
        caption="Cost bridge for the period"
        head={['Part', 'People', 'Amount']}
        rows={parts.map((part) => [
          LABELS[part.part],
          count(part.people),
          amountText(part, currency),
        ])}
      />
    </>
  );
}
