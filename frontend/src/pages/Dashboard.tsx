import { Box, Link, Stack, Typography } from '@mui/material';
import { type ReactNode, type RefObject, useId, useLayoutEffect, useRef } from 'react';
import { Link as RouterLink } from 'react-router';

import { exportInsight } from '../api/exports';
import { useInsight } from '../api/insights';
import type { InsightControl, InsightName } from '../api/types';
import { ExportMenu } from '../components/ExportMenu';
import { DashboardFilterBar } from '../components/filters/FilterBar';
import { controlQuery, useDashboardFilters } from '../components/filters/useDashboardFilters';
import { ByCountryCard } from '../components/insights/ByCountryCard';
import { ByDepartmentCard } from '../components/insights/ByDepartmentCard';
import { ByLevelCard } from '../components/insights/ByLevelCard';
import { ByTenureCard } from '../components/insights/ByTenureCard';
import { CardControl, CardSelect } from '../components/insights/CardControl';
import { CostBridgeCard } from '../components/insights/CostBridgeCard';
import { CostMixCard } from '../components/insights/CostMixCard';
import { DistributionCard } from '../components/insights/DistributionCard';
import { GenderGapCard } from '../components/insights/GenderGapCard';
import { KpiRow } from '../components/insights/KpiRow';
import { RateMonthLabel } from '../components/insights/RateMonthLabel';
import { TrendCard } from '../components/insights/TrendCard';
import { EmptyState } from '../components/layout/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';
import { formatDate } from '../lib/dates';
import { todayUtc } from '../lib/period';

const MEASURES = [
  { value: 'total_cost', label: 'Total cost' },
  { value: 'headcount', label: 'Headcount' },
] as const;
const VIEWS = [
  { value: 'cost', label: 'Cost' },
  { value: 'take_home', label: 'Take-home' },
] as const;
const GENDER_VIEWS = [
  { value: 'pay_gap', label: 'Pay gap' },
  { value: 'bonus', label: 'Bonus' },
  { value: 'quartiles', label: 'Quartiles' },
  { value: 'by_level', label: 'By level' },
] as const;
const LEVELS = [
  { value: 'all', label: 'All' },
  { value: '1', label: 'L1' },
  { value: '2', label: 'L2' },
  { value: '3', label: 'L3' },
  { value: '4', label: 'L4' },
  { value: '5', label: 'L5' },
  { value: '6', label: 'L6' },
] as const;

// The filter bar sticks only where the window has room for it and the cards below (D75). On a
// small or zoomed-in window it wraps to several lines and would cover most of the view, so there it
// scrolls away with the page.
const STICKY_ROOM = '@media (min-width: 1000px) and (min-height: 600px)';

/** While the bar sticks, main keeps that much room at its top when it scrolls a control into
 * view, so a control reached with the keyboard is never hidden under the bar (WCAG 2.4.11). */
function useRoomUnderStickyBar(bar: RefObject<HTMLDivElement | null>) {
  useLayoutEffect(() => {
    const element = bar.current;
    const main = element?.closest('main');
    if (!element || !main) return;
    const fit = () => {
      const sticky = getComputedStyle(element).position === 'sticky';
      main.style.scrollPaddingTop = sticky ? `${element.offsetHeight}px` : '';
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    window.addEventListener('resize', fit);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', fit);
      main.style.scrollPaddingTop = '';
    };
  }, [bar]);
}

/** The questions of SPEC section 9 for the filters in the URL (SPEC F5), under three headings
 * (D62), over the bar's period (D64). Each card is its own query, so a filter change refetches
 * every card, and a card's own control refetches that card alone. */
export function Dashboard() {
  const { filters, params, controls, set, setControl, reset, filtered } = useDashboardFilters();
  const barRef = useRef<HTMLDivElement>(null);
  useRoomUnderStickyBar(barRef);
  const trendControl = controlQuery('trend', controls);
  const tenureControl = controlQuery('tenure', controls);
  const mixControl = controlQuery('mix', controls);
  const gapControl = controlQuery('gap', controls);
  const summary = useInsight('summary', params);
  const trend = useInsight('trend', params, trendControl);
  const costBridge = useInsight('cost-bridge', params);
  const byCountry = useInsight('by-country', params);
  const byDepartment = useInsight('by-department', params);
  const costMix = useInsight('cost-mix', params, mixControl);
  const distribution = useInsight('distribution', params);
  const byLevel = useInsight('by-level', params);
  const byTenure = useInsight('by-tenure', params, tenureControl);
  const genderGap = useInsight('gender-gap', params, gapControl);
  const nobody = summary.data?.headcount === 0;
  // The population is the one on the period's last day, today unless the period ends earlier.
  const lastDay = summary.data?.to;
  const when = !lastDay || lastDay === todayUtc() ? 'today' : `on ${formatDate(lastDay)}`;
  // Every insight downloads from where it is shown, with the filters and its control on screen
  // (SPEC F6, D62).
  const exportMenu = (name: InsightName, label: string, what: string, control?: InsightControl) => (
    <ExportMenu
      size="small"
      label={label}
      what={what}
      name={name}
      onExport={(file) => exportInsight(name, params, file, control)}
    />
  );

  return (
    <>
      <PageHeader title="Dashboard" />
      {/* The filters decide every card, so they stay in view as the cards scroll (D75): stuck to
          the top of main, across its padding, on the page background with a hairline under them,
          above the charts and below the menus they open. */}
      <Box
        ref={barRef}
        sx={{
          // A sticky box stops at main's padding, so it is held up by that much to sit flush with
          // main's top edge.
          [STICKY_ROOM]: { position: 'sticky', top: (theme) => theme.spacing(-6) },
          zIndex: 'appBar',
          mx: -6,
          px: 6,
          pt: 3,
          mb: 4,
          bgcolor: 'background.default',
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <DashboardFilterBar
          filters={filters}
          onChange={set}
          onReset={reset}
          filtered={filtered}
          aside={
            <Link
              component={RouterLink}
              to="/help#hidden-figures"
              variant="body2"
              color="text.secondary"
              underline="hover"
            >
              Why are some figures hidden?
            </Link>
          }
        />
      </Box>
      <Section title="What we spend">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          {summary.data ? (
            <RateMonthLabel rateMonth={summary.data.rate_month} on={summary.data.to} />
          ) : null}
          {/* The summary has no card, so its menu sits on the rate month line above it (D60). */}
          <Box sx={{ ml: 'auto' }}>{exportMenu('summary', 'Export summary', 'the summary')}</Box>
        </Box>
        <KpiRow query={summary} includeExited={filters.include_exited} />
        {nobody ? (
          <EmptyState message={`No one matches these filters ${when}. Clear a filter.`} />
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
            <CostBridgeCard
              query={costBridge}
              includeExited={filters.include_exited}
              actions={exportMenu('cost-bridge', 'Export cost bridge', 'the cost bridge')}
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
            <CostMixCard
              query={costMix}
              actions={
                <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                  <CardControl
                    label="Cost mix view"
                    value={controls.mix}
                    options={VIEWS}
                    onChange={(view) => setControl('mix', view)}
                  />
                  {exportMenu('cost-mix', 'Export cost mix', 'the cost mix', mixControl)}
                </Stack>
              }
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
              <ByTenureCard
                query={byTenure}
                actions={
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                    <CardSelect
                      label="Level"
                      value={controls.tenure}
                      options={LEVELS}
                      onChange={(level) => setControl('tenure', level)}
                    />
                    {exportMenu(
                      'by-tenure',
                      'Export pay by tenure',
                      'the pay by tenure',
                      tenureControl,
                    )}
                  </Stack>
                }
              />
            </CardGrid>
          </Section>
          <Section title="Is pay fair">
            <CardGrid>
              <GenderGapCard
                query={genderGap}
                actions={
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start' }}>
                    <CardControl
                      label="Gender gap view"
                      value={controls.gap}
                      options={GENDER_VIEWS}
                      onChange={(view) => setControl('gap', view)}
                    />
                    {exportMenu(
                      'gender-gap',
                      'Export gender pay gap',
                      'the gender pay gap',
                      gapControl,
                    )}
                  </Stack>
                }
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
