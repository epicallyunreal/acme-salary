import { Box, Paper, Skeleton, Typography } from '@mui/material';
import type { UseQueryResult } from '@tanstack/react-query';
import { type ReactNode, useId } from 'react';

import { visuallyHidden } from '../../lib/a11y';
import { ErrorState } from '../layout/ErrorState';

interface InsightCardProps {
  /** SPEC section 9's question, the card's heading. */
  question: string;
  /** What failed to load, for the error state: "the payroll by country". */
  what: string;
  query: Pick<UseQueryResult, 'isPending' | 'isError' | 'refetch'>;
  /** The export menu goes here (step 7). */
  actions?: ReactNode;
  /** Spans both columns of the grid. */
  wide?: boolean;
  children: ReactNode;
}

export function InsightCard({ question, what, query, actions, wide, children }: InsightCardProps) {
  const headingId = useId();
  return (
    <Paper
      component="section"
      variant="outlined"
      aria-labelledby={headingId}
      sx={{ p: 4, minWidth: 0, gridColumn: wide ? { lg: '1 / -1' } : undefined }}
    >
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
          mb: 3,
        }}
      >
        <Typography
          id={headingId}
          component="h2"
          sx={{ fontSize: 16, lineHeight: '24px', fontWeight: 600 }}
        >
          {question}
        </Typography>
        {actions}
      </Box>
      {query.isError ? (
        <ErrorState what={what} onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <Skeleton variant="rounded" height={220} aria-label={`Loading ${what}`} />
      ) : (
        children
      )}
    </Paper>
  );
}

interface ChartTableProps {
  caption: string;
  head: string[];
  rows: (string | number)[][];
}

/** The chart's figures as text for screen readers, every row included: the chart is the
 * supplement and the table the record (ui-ux-pro-max's chart guidance). */
export function ChartTable({ caption, head, rows }: ChartTableProps) {
  return (
    <Box component="table" sx={visuallyHidden}>
      <caption>{caption}</caption>
      <thead>
        <tr>
          {head.map((cell) => (
            <th key={cell} scope="col">
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={String(row[0])}>
            {row.map((cell, index) =>
              index === 0 ? (
                <th key={index} scope="row">
                  {cell}
                </th>
              ) : (
                <td key={index}>{cell}</td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </Box>
  );
}

/** The panel a chart's tooltip shows for one mark. */
export function ChartTooltip({ title, lines }: { title: string; lines: string[] }) {
  return (
    <Paper variant="outlined" sx={{ px: 2, py: 1.5 }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600 }}>{title}</Typography>
      {lines.map((line) => (
        <Typography key={line} className="num" sx={{ fontSize: 12, color: 'text.secondary' }}>
          {line}
        </Typography>
      ))}
    </Paper>
  );
}

/** A short line under a chart, for what the chart leaves out. */
export function ChartNote({ children }: { children: ReactNode }) {
  return (
    <Typography variant="body2" sx={{ color: 'text.secondary', mt: 2 }}>
      {children}
    </Typography>
  );
}
