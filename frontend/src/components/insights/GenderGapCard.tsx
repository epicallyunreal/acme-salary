import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
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

import type {
  BonusInsight,
  BonusRow,
  BonusSide,
  GapRow,
  GenderGapInsight,
  LevelGapsInsight,
  LevelOthers,
  PayGapInsight,
  QuartilesInsight,
} from '../../api/types';
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
import {
  count,
  GAP_FLAG,
  GAP_FLAG_NOTE,
  GENDER_NOTE,
  genderMoney,
  SMALL_GROUP,
  SPREAD_GROUP,
} from './figures';
import { ChartNote, ChartTable, ChartTooltip, InsightCard } from './InsightCard';

const SERIES_LABEL: Record<string, string> = { female: 'Female', male: 'Male' };
const QUARTILES = ['Lower quartile', 'Lower middle', 'Upper middle', 'Upper quartile'];

/** A gap: `12.5%`, why it is withheld, or `—` for a group with nobody in it. */
function percent(value: string | null, reason: string | null): string {
  return value === null ? (reason ?? '—') : `${value}%`;
}

/** Question 6 on annual pay (D62): the pay gap, the bonus, the pay quartiles and the gap within
 * each level, as the card's control picks. Other and undisclosed are counted beside each. */
export function GenderGapCard({
  query,
  actions,
}: {
  query: UseQueryResult<GenderGapInsight>;
  actions?: ReactNode;
}) {
  return (
    <InsightCard
      question="Is there a gender pay gap? (on annual pay)"
      what="the gender pay gap"
      query={query}
      actions={actions}
      wide
    >
      {query.data ? (
        <>
          <Typography variant="body2" sx={{ color: 'text.secondary', mb: 2 }}>
            {GENDER_NOTE}
          </Typography>
          <GenderView data={query.data} />
        </>
      ) : null}
    </InsightCard>
  );
}

function GenderView({ data }: { data: GenderGapInsight }) {
  switch (data.view) {
    case 'bonus':
      return <BonusView data={data} />;
    case 'quartiles':
      return <QuartilesView data={data} />;
    case 'by_level':
      return <LevelView data={data} />;
    default:
      return <PayGapView data={data} />;
  }
}

/** The gap above its pair, a line for each one given: the pair spans from the female bar to
 * this male bar, so its middle is half a gap to the left of this bar's left edge. */
function GapLabel({ x, value }: LabelProps) {
  const middle = Number(x) - BAR_GAP / 2;
  return (
    <text
      x={middle}
      y={14}
      textAnchor="middle"
      fill={tokens.inkSecondary}
      fontSize={12}
      style={{ fontVariantNumeric: 'tabular-nums' }}
    >
      {String(value)
        .split('\n')
        .map((line, index) => (
          <tspan key={line} x={middle} dy={index ? '1.2em' : 0}>
            {line}
          </tspan>
        ))}
    </text>
  );
}

function payGap(row: GapRow): string {
  return percent(row.gap_pct, row.reason);
}

function PayGapView({ data }: { data: PayGapInsight }) {
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
      gap: payGap(row),
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
                    `Female: ${count(row.female.headcount)}, median ${genderMoney(row.female.median_gross, currency, row.female.headcount, 'women')}`,
                    `Male: ${count(row.male.headcount)}, median ${genderMoney(row.male.median_gross, currency, row.male.headcount, 'men')}`,
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
          genderMoney(row.female.median_gross, currency, row.female.headcount, 'women'),
          count(row.male.headcount),
          genderMoney(row.male.median_gross, currency, row.male.headcount, 'men'),
          count(row.other_count),
          count(row.undisclosed_count),
          payGap(row),
        ])}
      />
    </>
  );
}

/** `5 of 6 (83.3%)`, or the group's reason when its women and men cannot be compared. */
function receiving(side: BonusSide, reason: string | null): string {
  if (side.receiving === null || side.receiving_pct === null) return reason ?? '';
  return `${count(side.receiving)} of ${count(side.headcount)} (${side.receiving_pct}%)`;
}

function bonusGap(row: BonusRow, which: 'mean_gap_pct' | 'median_gap_pct'): string {
  return percent(row[which], row.reason);
}

/** The gaps above a pair, mean over median, or why they are withheld. */
function bonusGaps(row: BonusRow): string {
  if (row.mean_gap_pct === null) return row.reason ?? '—';
  return `Mean ${row.mean_gap_pct}%\nMedian ${row.median_gap_pct}%`;
}

function BonusView({ data }: { data: BonusInsight }) {
  const shown = data.rows.filter((row) => row.female.receiving_pct !== null);
  const bars = shown.map((row) => ({
    row,
    label: row.country?.name ?? 'Overall',
    female: plot(row.female.receiving_pct),
    male: plot(row.male.receiving_pct),
    gaps: bonusGaps(row),
  }));
  return (
    <>
      {bars.length ? (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={bars}
            barGap={BAR_GAP}
            margin={{ top: 40, right: 16, bottom: 0, left: 0 }}
          >
            <CartesianGrid vertical={false} {...GRID} />
            <XAxis dataKey="label" {...AXIS} />
            <YAxis
              domain={[0, 100]}
              tickFormatter={(value: number) => `${value}%`}
              width={48}
              {...AXIS}
            />
            <Tooltip
              cursor={CURSOR}
              content={({ active, payload }) => {
                const item = payload?.[0]?.payload as (typeof bars)[number] | undefined;
                if (!active || !item) return null;
                const { row } = item;
                return (
                  <ChartTooltip
                    title={item.label}
                    lines={[
                      `Women with a bonus: ${receiving(row.female, row.reason)}`,
                      `Men with a bonus: ${receiving(row.male, row.reason)}`,
                      `Mean gap ${bonusGap(row, 'mean_gap_pct')}`,
                      `Median gap ${bonusGap(row, 'median_gap_pct')}`,
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
            <Bar
              dataKey="male"
              fill={SERIES[1]}
              maxBarSize={BAR_SIZE}
              radius={ROUND_TOP}
              {...STILL}
            >
              <LabelList dataKey="gaps" content={GapLabel} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : null}
      <TableContainer>
        <Table size="small" aria-label="Bonus by gender">
          <TableHead>
            <TableRow>
              <TableCell>Country</TableCell>
              <TableCell>Women with a bonus</TableCell>
              <TableCell>Men with a bonus</TableCell>
              <TableCell>Mean bonus gap</TableCell>
              <TableCell>Median bonus gap</TableCell>
              <TableCell>Other, undisclosed</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.rows.map((row) => (
              <TableRow key={row.country?.code ?? 'overall'}>
                <TableCell component="th" scope="row">
                  {row.country?.name ?? 'Overall'}
                </TableCell>
                <TableCell className="num">{receiving(row.female, row.reason)}</TableCell>
                <TableCell className="num">{receiving(row.male, row.reason)}</TableCell>
                <TableCell className="num">{bonusGap(row, 'mean_gap_pct')}</TableCell>
                <TableCell className="num">{bonusGap(row, 'median_gap_pct')}</TableCell>
                <TableCell className="num">
                  {count(row.other_count)}, {count(row.undisclosed_count)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}

function QuartilesView({ data }: { data: QuartilesInsight }) {
  // Other and undisclosed are counted beside the quartiles, never ranked in them (D62).
  const unranked = (
    <ChartNote>
      Not ranked, counted beside: {count(data.other_count)} other and{' '}
      {count(data.undisclosed_count)} undisclosed.
    </ChartNote>
  );
  if (data.quartiles === null) {
    return (
      <>
        <ChartNote>
          {data.headcount === 0
            ? 'No women or men match these filters.'
            : `Shown for ${SPREAD_GROUP} women and men or more, with ${SMALL_GROUP} of each; these filters have ${data.reason}.`}
        </ChartNote>
        {unranked}
      </>
    );
  }
  const bars = data.quartiles.map((quartile) => ({
    quartile,
    label: QUARTILES[quartile.quartile - 1],
    female: quartile.female,
    male: quartile.male,
  }));
  return (
    <>
      <ResponsiveContainer width="100%" height={200}>
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
          <YAxis type="category" dataKey="label" width={110} {...AXIS} />
          <Tooltip
            cursor={CURSOR}
            content={({ active, payload }) => {
              const item = payload?.[0]?.payload as (typeof bars)[number] | undefined;
              if (!active || !item) return null;
              const { quartile } = item;
              return (
                <ChartTooltip
                  title={item.label}
                  lines={[
                    `Women: ${count(quartile.female)} (${quartile.female_pct}%)`,
                    `Men: ${count(quartile.male)} (${quartile.male_pct}%)`,
                  ]}
                />
              );
            }}
          />
          <Legend
            formatter={(value: string) => ({ female: 'Women', male: 'Men' })[value] ?? value}
          />
          <Bar dataKey="female" stackId="q" fill={SERIES[0]} maxBarSize={BAR_SIZE} {...STILL} />
          <Bar dataKey="male" stackId="q" fill={SERIES[1]} maxBarSize={BAR_SIZE} {...STILL} />
        </BarChart>
      </ResponsiveContainer>
      <ChartNote>
        Women and men in these filters ranked by gross pay and split into four equal groups, the
        lowest first.
      </ChartNote>
      {unranked}
      <ChartTable
        caption="Pay quartiles by gender"
        head={['Quartile', 'Women', 'Men']}
        rows={data.quartiles.map((quartile) => [
          QUARTILES[quartile.quartile - 1],
          `${count(quartile.female)} (${quartile.female_pct}%)`,
          `${count(quartile.male)} (${quartile.male_pct}%)`,
        ])}
      />
    </>
  );
}

/** Other and undisclosed, counted per country beside the levels, never per level (D62). */
function unrankedByCountry(others: LevelOthers[]): string {
  const counted = others.filter((row) => row.other_count + row.undisclosed_count > 0);
  if (!counted.length) return 'No other or undisclosed employees in these filters.';
  const listed = counted.map(
    (row) =>
      `${row.country.name} ${count(row.other_count)} other, ${count(row.undisclosed_count)} undisclosed`,
  );
  return `Counted by country, not by level: ${listed.join('; ')}.`;
}

function LevelView({ data }: { data: LevelGapsInsight }) {
  const flagged = data.rows.some((row) => row.flagged);
  return (
    <>
      <TableContainer>
        <Table size="small" aria-label="Gender pay gap by level">
          <TableHead>
            <TableRow>
              <TableCell>Country and level</TableCell>
              <TableCell>Women</TableCell>
              <TableCell>Men</TableCell>
              <TableCell>Mean gap</TableCell>
              <TableCell>Median gap</TableCell>
              <TableCell>Flag</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.rows.map((row) => (
              <TableRow key={`${row.country.code}-${row.level}`}>
                <TableCell component="th" scope="row">
                  {row.country.name}, L{row.level}
                </TableCell>
                <TableCell className="num">{count(row.female.headcount)}</TableCell>
                <TableCell className="num">{count(row.male.headcount)}</TableCell>
                <TableCell className="num">{percent(row.mean_gap_pct, row.reason)}</TableCell>
                <TableCell className="num">{percent(row.median_gap_pct, row.reason)}</TableCell>
                <TableCell>{row.flagged ? GAP_FLAG : ''}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <ChartNote>{unrankedByCountry(data.others)}</ChartNote>
      {flagged ? <ChartNote>{GAP_FLAG_NOTE}</ChartNote> : null}
    </>
  );
}
