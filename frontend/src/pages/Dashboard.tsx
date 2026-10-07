import { Box } from '@mui/material';

import { useInsight } from '../api/insights';
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

  return (
    <>
      <PageHeader title="Dashboard" />
      <DashboardFilterBar filters={filters} onChange={set} onReset={reset} filtered={filtered} />
      {summary.data ? <RateMonthLabel rateMonth={summary.data.rate_month} /> : null}
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
          <ByCountryCard query={byCountry} />
          <ByDepartmentCard query={byDepartment} />
          <DistributionCard query={distribution} />
          <ByLevelCard query={byLevel} />
          <GenderGapCard query={genderGap} />
        </Box>
      )}
    </>
  );
}
