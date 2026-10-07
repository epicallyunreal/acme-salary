import { Box } from '@mui/material';

import { exportInsight } from '../api/exports';
import { useInsight } from '../api/insights';
import type { InsightName } from '../api/types';
import { ExportMenu } from '../components/ExportMenu';
import { DashboardFilterBar } from '../components/filters/FilterBar';
import { useDashboardFilters } from '../components/filters/useDashboardFilters';
import { ByCountryCard } from '../components/insights/ByCountryCard';
import { ByDepartmentCard } from '../components/insights/ByDepartmentCard';
import { ByLevelCard } from '../components/insights/ByLevelCard';
import { DistributionCard } from '../components/insights/DistributionCard';
import { GenderGapCard } from '../components/insights/GenderGapCard';
import { KpiRow } from '../components/insights/KpiRow';
import { RateMonthLabel } from '../components/insights/RateMonthLabel';
import { EmptyState } from '../components/layout/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';

/** The six questions of SPEC section 9 for the filters in the URL (SPEC F5). Each card is its
 * own query, so a filter change refetches every card. */
export function Dashboard() {
  const { filters, set, reset, filtered } = useDashboardFilters();
  const summary = useInsight('summary', filters);
  const byCountry = useInsight('by-country', filters);
  const byDepartment = useInsight('by-department', filters);
  const distribution = useInsight('distribution', filters);
  const byLevel = useInsight('by-level', filters);
  const genderGap = useInsight('gender-gap', filters);
  const nobody = summary.data?.headcount === 0;
  // Every insight downloads from where it is shown, with the filters on screen (SPEC F6).
  const exportMenu = (name: InsightName, label: string, what: string) => (
    <ExportMenu label={label} what={what} onExport={(file) => exportInsight(name, filters, file)} />
  );

  return (
    <>
      <PageHeader title="Dashboard" />
      <DashboardFilterBar filters={filters} onChange={set} onReset={reset} filtered={filtered} />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        {summary.data ? <RateMonthLabel rateMonth={summary.data.rate_month} /> : null}
        {/* The summary has no card, so its menu sits on the rate month line above it (D60). */}
        <Box sx={{ ml: 'auto' }}>{exportMenu('summary', 'Export summary', 'the summary')}</Box>
      </Box>
      <KpiRow query={summary} />
      {nobody ? (
        <EmptyState message="No one matches these filters today. Clear a filter." />
      ) : (
        <Box
          sx={{
            display: 'grid',
            gap: 3,
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'repeat(2, minmax(0, 1fr))' },
          }}
        >
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
          <GenderGapCard
            query={genderGap}
            actions={exportMenu('gender-gap', 'Export gender pay gap', 'the gender pay gap')}
          />
        </Box>
      )}
    </>
  );
}
