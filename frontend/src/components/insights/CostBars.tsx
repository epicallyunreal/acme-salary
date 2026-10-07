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

import { tokens } from '../../lib/theme';
import {
  AXIS,
  BAR_SIZE,
  compactTick,
  CURSOR,
  GRID,
  ROUND_RIGHT,
  SERIES,
  STILL,
} from './chartTheme';
import { ChartTooltip } from './InsightCard';

export interface CostBar {
  name: string;
  cost: number;
  /** At the bar's tip: a share, or the figure. */
  label: string;
  /** The tooltip's lines. */
  lines: string[];
}

/** Total cost as horizontal bars, one per group, largest first as the API orders them. */
export function CostBars({ bars, currency }: { bars: CostBar[]; currency: string }) {
  return (
    <ResponsiveContainer width="100%" height={bars.length * 36 + 32}>
      <BarChart data={bars} layout="vertical" margin={{ top: 0, right: 80, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} {...GRID} />
        <XAxis type="number" tickFormatter={compactTick(currency)} {...AXIS} />
        <YAxis type="category" dataKey="name" width={130} {...AXIS} />
        <Tooltip
          cursor={CURSOR}
          content={({ active, payload }) => {
            const bar = payload?.[0]?.payload as CostBar | undefined;
            return active && bar ? <ChartTooltip title={bar.name} lines={bar.lines} /> : null;
          }}
        />
        <Bar dataKey="cost" fill={SERIES[0]} maxBarSize={BAR_SIZE} radius={ROUND_RIGHT} {...STILL}>
          <LabelList dataKey="label" position="right" fill={tokens.inkSecondary} fontSize={12} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
