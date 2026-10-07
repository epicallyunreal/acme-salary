import { Box, Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { DistributionInsight } from '../../api/types';
import { formatMoney } from '../../lib/money';
import {
  AXIS,
  BAR_GAP,
  compactTick,
  CURSOR,
  GRID,
  MARKER,
  ROUND_TOP,
  SERIES,
  STILL,
} from './chartTheme';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

const MARKERS = [
  ['p10', 'p10'],
  ['p50', 'median'],
  ['p90', 'p90'],
] as const;

/** Question 4: gross in twelve equal bands from p1 to p99, with p10, the median and p90 marked. */
export function DistributionCard({ query }: { query: UseQueryResult<DistributionInsight> }) {
  return (
    <InsightCard
      question="How are salaries distributed?"
      what="the salary distribution"
      query={query}
    >
      {query.data ? <Distribution data={query.data} /> : null}
    </InsightCard>
  );
}

function Distribution({ data }: { data: DistributionInsight }) {
  const { currency, bands, markers, p1, p99 } = data;
  if (!bands || !markers || p1 === null || p99 === null) {
    return (
      <ChartNote>
        {data.headcount === 0
          ? 'Nobody matches these filters.'
          : `Shown for 5 people or more; these filters match ${data.headcount}.`}
      </ChartNote>
    );
  }
  const table = (
    <ChartTable
      caption="Salary distribution"
      head={['Band', 'From', 'To', 'People']}
      rows={bands.map((band) => [
        `Band ${band.index + 1}`,
        formatMoney(band.from, currency),
        formatMoney(band.to, currency),
        band.count,
      ])}
    />
  );
  if (bands.length === 1) {
    return (
      <>
        <ChartNote>
          All {data.headcount} people in these filters earn {formatMoney(p1, currency)}.
        </ChartNote>
        {table}
      </>
    );
  }
  // A number axis, so each marker sits at its own value rather than at a band's middle.
  // Recharts leaves the category gap on each side of a bar, so half of it makes the 2 px gap.
  const rows = bands.map((band) => ({
    band,
    middle: (Number(band.from) + Number(band.to)) / 2,
    count: band.count,
  }));
  return (
    <>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={rows}
          barCategoryGap={BAR_GAP / 2}
          margin={{ top: 20, right: 16, bottom: 0, left: 0 }}
        >
          <CartesianGrid vertical={false} {...GRID} />
          <XAxis
            type="number"
            dataKey="middle"
            domain={[Number(p1), Number(p99)]}
            ticks={[Number(p1), Number(markers.p50), Number(p99)]}
            tickFormatter={compactTick(currency)}
            {...AXIS}
          />
          <YAxis allowDecimals={false} width={32} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof rows)[number] | undefined;
              if (!active || !item) return null;
              return (
                <ChartTooltip
                  title={`${formatMoney(item.band.from, currency)} to ${formatMoney(item.band.to, currency)}`}
                  lines={[`${item.band.count} people`]}
                />
              );
            }}
          />
          <Bar dataKey="count" fill={SERIES[0]} radius={ROUND_TOP} {...STILL} />
          {MARKERS.map(([key, label]) => (
            <ReferenceLine
              key={key}
              x={Number(markers[key])}
              stroke={MARKER}
              strokeDasharray="3 3"
              label={{ value: label, position: 'top', fill: MARKER, fontSize: 12 }}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <Box component="p" sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, m: 0, mt: 2 }}>
        {MARKERS.map(([key, label]) => (
          <Typography
            key={key}
            component="span"
            variant="body2"
            className="num"
            sx={{ color: 'text.secondary' }}
          >
            {label} {formatMoney(markers[key], currency)}
          </Typography>
        ))}
      </Box>
      {table}
    </>
  );
}
