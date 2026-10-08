import { Box, Stack, Typography } from '@mui/material';
import { type ReactNode, useId } from 'react';

import { exportInsight } from '../api/exports';
import { useInsight } from '../api/insights';
import type { InsightControl, InsightName } from '../api/types';
import { ExportMenu } from '../components/ExportMenu';
import { DashboardFilterBar } from '../components/filters/FilterBar';
import { controlQuery, useDashboardFilters } from '../components/filters/useDashboardFilters';
import { ByCountryCard } from '../components/insights/ByCountryCard';
import { ByDepartmentCard } from '../components/insights/ByDepartmentCard';
import { ByLevelCard } from '../components/insights/ByLevelCard';
import { CardControl } from '../components/insights/CardControl';
import { DistributionCard } from '../components/insights/DistributionCard';
import { GenderGapCard } from '../components/insights/GenderGapCard';
import { KpiRow } from '../components/insights/KpiRow';
import { RateMonthLabel } from '../components/insights/RateMonthLabel';
import { TrendCard } from '../components/insights/TrendCard';
import { EmptyState } from '../components/layout/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';

const MEASURES = [
  { value: 'total_cost', label: 'Total cost' },
  { value: 'headcount', label: 'Headcount' },
] as const;

/** The questions of SPEC section 9 for the filters in the URL (SPEC F5), under three headings
 * (D62). Each card is its own query, so a filter change refetches every card, and a card's own
 * control refetches that card alone. */
export function Dashboard() {
  const { filters, controls, set, setControl, reset, filtered } = useDashboardFilters();
  const trendControl = controlQuery('trend', controls);
  const summary = useInsight('summary', filters);
  const trend = useInsight('trend', filters, trendControl);
  const byCountry = useInsight('by-country', filters);
  const byDepartment = useInsight('by-department', filters);
  const distribution = useInsight('distribution', filters);
  const byLevel = useInsight('by-level', filters);
  const genderGap = useInsight('gender-gap', filters);
  const nobody = summary.data?.headcount === 0;
  // Every insight downloads from where it is shown, with the filters and its control on screen
  // (SPEC F6, D62).
  const exportMenu = (name: InsightName, label: string, what: string, control?: InsightControl) => (
    <ExportMenu
      size="small"
      label={label}
      what={what}
      onExport={(file) => exportInsight(name, filters, file, control)}
    />
  );

  return (
    <>
      <PageHeader title="Dashboard" />
      <DashboardFilterBar filters={filters} onChange={set} onReset={reset} filtered={filtered} />
      <Section title="What we spend">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          {summary.data ? <RateMonthLabel rateMonth={summary.data.rate_month} /> : null}
          {/* The summary has no card, so its menu sits on the rate month line above it (D60). */}
          <Box sx={{ ml: 'auto' }}>{exportMenu('summary', 'Export summary', 'the summary')}</Box>
        </Box>
        <KpiRow query={summary} />
        {nobody ? (
          <EmptyState message="No one matches these filters today. Clear a filter." />
        ) : (
          <CardGrid>
            <TrendCard
              query={trend}
              measure={controls.trend}
              includeExited={filters.include_exited}
              actions={
                <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                  <CardControl
                    label="Trend measure"
                    value={controls.trend}
                    options={MEASURES}
                    onChange={(measure) => setControl('trend', measure)}
                  />
                  {exportMenu('trend', 'Export cost trend', 'the cost trend', trendControl)}
                </Stack>
              }
            />
            <ByCountryCard
              query={byCountry}
              actions={exportMenu(
                'by-country',
                'Export payroll by country',
                'the payroll by country',
              )}
            />
            <ByDepartmentCard
              query={byDepartment}
              actions={exportMenu(
                'by-department',
                'Export payroll by department',
                'the payroll by department',
              )}
            />
          </CardGrid>
        )}
      </Section>
      {nobody ? null : (
        <>
          <Section title="How pay is structured">
            <CardGrid>
              <DistributionCard
                query={distribution}
                actions={exportMenu(
                  'distribution',
                  'Export salary distribution',
                  'the salary distribution',
                )}
              />
              <ByLevelCard
                query={byLevel}
                actions={exportMenu('by-level', 'Export pay by level', 'the pay by level')}
              />
            </CardGrid>
          </Section>
          <Section title="Is pay fair">
            <CardGrid>
              <GenderGapCard
                query={genderGap}
                actions={exportMenu('gender-gap', 'Export gender pay gap', 'the gender pay gap')}
              />
            </CardGrid>
          </Section>
        </>
      )}
    </>
  );
}

/** One of the dashboard's three groups of cards, named by its heading (D62). */
function Section({ title, children }: { title: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <Box component="section" aria-labelledby={headingId} sx={{ mb: 5 }}>
      <Typography
        id={headingId}
        component="h2"
        sx={{ fontSize: 20, lineHeight: '28px', fontWeight: 600, mb: 3 }}
      >
        {title}
      </Typography>
      {children}
    </Box>
  );
}

function CardGrid({ children }: { children: ReactNode }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gap: 3,
        gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'repeat(2, minmax(0, 1fr))' },
      }}
    >
      {children}
    </Box>
  );
}
