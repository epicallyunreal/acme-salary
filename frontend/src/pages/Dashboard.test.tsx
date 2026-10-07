import { screen, waitFor } from '@testing-library/react';
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
];
const INSIGHTS = [
  'by-country',
  'by-department',
  'by-level',
  'distribution',
  'gender-gap',
  'summary',
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

describe('Dashboard', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('answers the six questions for the whole company', async () => {
    renderApp('/');

    expect(await screen.findByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(await screen.findByText('27')).toBeInTheDocument();
    expect(screen.getByText('October 2026 rates')).toBeInTheDocument();
    for (const question of QUESTIONS) {
      expect(await screen.findByRole('heading', { level: 2, name: question })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('aria-current', 'page');
  });

  it('a filter change refetches every card with the new filter', async () => {
    const seen = recordRequests();
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('27');

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
    expect(await screen.findByText('27')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'Include exited' }));

    // The fixture's two exited employees, X1 and X2, now count.
    expect(await screen.findByText('29')).toBeInTheDocument();
    expect(screen.queryByText('27')).not.toBeInTheDocument();
  });

  it('offers the local currency only while one country is selected', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByText('27');

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

    expect(await screen.findByText('29')).toBeInTheDocument();
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
