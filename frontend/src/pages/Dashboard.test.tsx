import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../lib/auth';
import { insightFor, nobody } from '../test/fixtures/insights';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

const QUESTIONS = [
  'Where does payroll go, by country?',
  'Which departments cost most and pay most?',
  'How are salaries distributed?',
  'What does each level pay?',
  'Is there a gender pay gap?',
  'How has total cost moved over two years?',
];
const SECTIONS = ['What we spend', 'How pay is structured', 'Is pay fair'];
const INSIGHTS = [
  'by-country',
  'by-department',
  'by-level',
  'distribution',
  'gender-gap',
  'summary',
  'trend',
];

/** Answers every insight from the fixtures and records the query string of each request. */
function recordRequests() {
  const seen: Record<string, URLSearchParams[]> = {};
  server.use(
    http.get('/api/v1/insights/:name/', ({ request, params }) => {
      const name = String(params.name);
      const query = new URL(request.url).searchParams;
      (seen[name] ??= []).push(query);
      return HttpResponse.json(insightFor(name, query.get('include_exited') === 'true'));
    }),
  );
  return seen;
}

/** Answers every insight in the currency the request asks for, as the API would. */
function answerInTheAskedCurrency() {
  const local: Record<string, string> = { IN: 'INR', DE: 'EUR' };
  server.use(
    http.get('/api/v1/insights/:name/', ({ request, params }) => {
      const query = new URL(request.url).searchParams;
      const asked = query.get('currency') ?? 'usd';
      const code = asked === 'local' ? local[query.get('country') ?? ''] : asked.toUpperCase();
      const payload = insightFor(String(params.name), false) as Record<string, unknown>;
      const rateMonth =
        asked === 'local'
          ? { label: `local currency (${code})`, effective_from: null }
          : payload.rate_month;
      return HttpResponse.json({ ...payload, currency: code, rate_month: rateMonth });
    }),
  );
}

async function keyFigures() {
  return screen.findByRole('region', { name: 'Key figures' });
}

describe('Dashboard', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('answers every question for the whole company, under three headings', async () => {
    renderApp('/');

    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(await within(await keyFigures()).findByText('27')).toBeInTheDocument();
    expect(screen.getByText('October 2026 rates')).toBeInTheDocument();
    for (const section of SECTIONS) {
      expect(await screen.findByRole('heading', { level: 2, name: section })).toBeInTheDocument();
    }
    for (const question of QUESTIONS) {
      expect(await screen.findByRole('heading', { level: 3, name: question })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
  });

  it('a filter change refetches every card with the new filter', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    renderApp('/');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(Object.keys(seen).sort()).toEqual(INSIGHTS);
      for (const name of INSIGHTS) {
        expect(seen[name].map((query) => query.get('country'))).toContain('IN');
      }
    });
  });

  it("the include-exited box adds the filter's exited employees to the headcount", async () => {
    const user = userEvent.setup();
    renderApp('/');
    const kpis = await keyFigures();
    expect(await within(kpis).findByText('27')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'Include exited' }));

    // The fixture's two exited employees, X1 and X2, now count.
    expect(await within(kpis).findByText('29')).toBeInTheDocument();
    expect(within(kpis).queryByText('27')).not.toBeInTheDocument();
  });

  it('offers the local currency only while one country is selected', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await within(await keyFigures()).findByText('27');

    await user.click(screen.getByLabelText('Currency'));
    expect(await screen.findByRole('option', { name: 'EUR' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Local' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');
    await user.click(screen.getByLabelText('Currency'));

    expect(await screen.findByRole('option', { name: 'Local' })).toBeInTheDocument();
  });

  it('reads its filters from the URL and sends them with every card', async () => {
    const seen = recordRequests();
    renderApp('/?country=IN&currency=local&include_exited=true');

    expect(await within(await keyFigures()).findByText('29')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Include exited' })).toBeChecked();
    await waitFor(() => expect(Object.keys(seen).sort()).toEqual(INSIGHTS));
    for (const name of INSIGHTS) {
      const query = seen[name][0];
      expect([query.get('country'), query.get('currency'), query.get('include_exited')]).toEqual([
        'IN',
        'local',
        'true',
      ]);
    }
  });

  it('keeps local through a switch from India to Germany, and drops it for two countries', async () => {
    answerInTheAskedCurrency();
    const user = userEvent.setup();
    renderApp('/?country=IN&currency=local');
    const kpis = await keyFigures();
    expect(await screen.findByText('Local currency (INR)')).toBeInTheDocument();
    expect(within(kpis).getAllByText('INR')).toHaveLength(3);

    // India to Germany in one visit to the menu: still one country, so local stays.
    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.click(screen.getByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('Local currency (EUR)')).toBeInTheDocument();
    expect(within(kpis).getAllByText('EUR')).toHaveLength(3);

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'India' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('October 2026 rates')).toBeInTheDocument();
    expect(within(kpis).getAllByText('USD')).toHaveLength(3);
  });

  it('drops local when no country is left', async () => {
    answerInTheAskedCurrency();
    const user = userEvent.setup();
    renderApp('/?country=DE&currency=local');
    expect(await screen.findByText('Local currency (EUR)')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Country'));
    await user.click(await screen.findByRole('option', { name: 'Germany' }));
    await user.keyboard('{Escape}');

    expect(await screen.findByText('October 2026 rates')).toBeInTheDocument();
    expect(within(await keyFigures()).getAllByText('USD')).toHaveLength(3);
  });

  it("the trend's control picks its line, lives in the URL and refetches that card alone", async () => {
    const user = userEvent.setup();
    const seen = recordRequests();
    const { router } = renderApp('/');
    const control = await screen.findByRole('group', { name: 'Trend measure' });
    await waitFor(() => expect(seen.trend).toHaveLength(1));

    await user.click(within(control).getByRole('button', { name: 'Headcount' }));

    await waitFor(() => expect(seen.trend).toHaveLength(2));
    expect(seen.trend[1].get('measure')).toBe('headcount');
    expect(router.state.location.search).toBe('?trend.measure=headcount');
    expect(within(control).getByRole('button', { name: 'Headcount' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    for (const name of INSIGHTS.filter((insight) => insight !== 'trend')) {
      expect(seen[name]).toHaveLength(1);
    }
  });

  it("Clear filters resets the cards' controls with the bar's filters", async () => {
    const user = userEvent.setup();
    const { router } = renderApp('/?country=IN&trend.measure=headcount');

    await user.click(await screen.findByRole('button', { name: 'Clear filters' }));

    expect(router.state.location.search).toBe('');
    const control = await screen.findByRole('group', { name: 'Trend measure' });
    expect(within(control).getByRole('button', { name: 'Total cost' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('a card control alone still offers Clear filters', async () => {
    renderApp('/?trend.measure=headcount');

    expect(await screen.findByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });

  it('says what to do when no one matches the filters', async () => {
    server.use(
      http.get('/api/v1/insights/:name/', ({ params }) =>
        HttpResponse.json(
          params.name === 'summary' ? nobody : insightFor(String(params.name), false),
        ),
      ),
    );
    renderApp('/?country=NL');

    expect(
      await screen.findByText('No one matches these filters today. Clear a filter.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: QUESTIONS[0] })).not.toBeInTheDocument();
    // The filter bar's own button clears them.
    expect(screen.getByRole('button', { name: 'Clear filters' })).toBeInTheDocument();
  });
});
