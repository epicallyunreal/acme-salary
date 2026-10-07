import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../../lib/auth';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/setup';
import { EmployeeForm } from './EmployeeForm';

type User = ReturnType<typeof userEvent.setup>;

/** Fills the identity section; options arrive with the meta queries, so they are awaited. */
async function fillIdentity(user: User, country = 'India (INR)') {
  await user.type(screen.getByLabelText(/Full name/), 'Meera Iyer');
  await user.type(screen.getByLabelText(/Email/), 'meera@acme.example');
  await user.selectOptions(screen.getByLabelText(/Gender/), 'female');
  await screen.findByRole('option', { name: country });
  await user.selectOptions(screen.getByLabelText(/Country/), country);
  await screen.findByRole('option', { name: 'Engineering' });
  await user.selectOptions(screen.getByLabelText(/Department/), 'engineering');
  await user.type(screen.getByLabelText(/Designation/), 'Engineer');
  await user.selectOptions(screen.getByLabelText(/Level/), '2');
  fireEvent.change(screen.getByLabelText(/Joining date/), { target: { value: '2026-11-01' } });
}

describe('EmployeeForm', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('says what is missing when saved empty, in a summary that takes focus', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EmployeeForm />, { route: '/employees/new' });

    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    const summary = await screen.findByRole('alert');
    expect(summary).toHaveTextContent('The employee was not saved');
    expect(within(summary).getByRole('link', { name: 'Enter the full name' })).toBeInTheDocument();
    expect(within(summary).getByRole('link', { name: 'Choose a country' })).toBeInTheDocument();
    expect(within(summary).getByRole('link', { name: 'Choose a gender' })).toBeInTheDocument();
    expect(summary).toHaveFocus();
    expect(screen.getByLabelText(/Full name/)).toHaveAttribute('aria-invalid', 'true');
  });

  it("shows the chosen country's components", async () => {
    const user = userEvent.setup();
    renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    expect(screen.getByText('Choose a country to see its pay components.')).toBeInTheDocument();

    await screen.findByRole('option', { name: 'United States (USD)' });
    await user.selectOptions(screen.getByLabelText(/Country/), 'US');

    expect(await screen.findByLabelText(/Base salary \(USD\)/)).toBeInTheDocument();
    expect(screen.getByLabelText('Income tax (USD)')).toBeInTheDocument();
    expect(screen.queryByLabelText(/House rent allowance/)).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Country/), 'IN');

    expect(await screen.findByLabelText('House rent allowance (INR)')).toBeInTheDocument();
  });

  it("drops the old country's amounts when the country changes, so they cannot block the save", async () => {
    const user = userEvent.setup();
    const sent: { lines: unknown[] }[] = [];
    server.use(
      http.post('/api/v1/employees/', async ({ request }) => {
        sent.push((await request.json()) as { lines: unknown[] });
        return HttpResponse.json({ id: 5, warnings: [] }, { status: 201 });
      }),
    );
    const { router } = renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    await fillIdentity(user);
    await user.type(await screen.findByLabelText('House rent allowance (INR)'), 'abc');

    await user.selectOptions(screen.getByLabelText(/Country/), 'US');
    await user.type(await screen.findByLabelText(/Base salary \(USD\)/), '120000');
    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/employees/5'));
    expect(sent.map((body) => body.lines)).toEqual([
      [{ component: 'BASE', annual_amount: '120000' }],
    ]);
  });

  it('says when the countries or departments fail to load, with a retry', async () => {
    const user = userEvent.setup();
    let failures = 1;
    server.use(
      http.get('/api/v1/meta/countries/', () => {
        if (failures-- > 0) return HttpResponse.json({}, { status: 500 });
        return HttpResponse.json([
          { code: 'IN', name: 'India', currency_code: 'INR', min_gross_annual: '400000.00' },
        ]);
      }),
    );
    renderWithProviders(<EmployeeForm />, { route: '/employees/new' });

    expect(
      await screen.findByText(
        'Could not load the countries and departments. Check your connection and try again.',
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('option', { name: 'India (INR)' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('holds a note over 1,000 characters back, as the server would refuse it (D51)', async () => {
    const user = userEvent.setup();
    const sent: { note: string }[] = [];
    server.use(
      http.post('/api/v1/employees/', async ({ request }) => {
        sent.push((await request.json()) as { note: string });
        return HttpResponse.json({ id: 5, warnings: [] }, { status: 201 });
      }),
    );
    const { router } = renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    await fillIdentity(user);
    await user.type(await screen.findByLabelText(/Base salary \(INR\)/), '900000');
    const note = screen.getByLabelText(/Note/);
    fireEvent.change(note, { target: { value: 'n'.repeat(1001) } });

    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Use 1,000 characters or fewer');
    expect(note).toHaveAccessibleDescription('Use 1,000 characters or fewer');
    expect(sent).toEqual([]);

    fireEvent.change(note, { target: { value: 'n'.repeat(1000) } });
    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/employees/5'));
    expect(sent.map((body) => body.note.length)).toEqual([1000]);
  });

  it('previews gross, net and total cost as the amounts are typed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    await screen.findByRole('option', { name: 'India (INR)' });
    await user.selectOptions(screen.getByLabelText(/Country/), 'IN');

    await user.type(await screen.findByLabelText(/Base salary \(INR\)/), '1000000');
    await user.type(screen.getByLabelText('House rent allowance (INR)'), '400000');
    await user.type(screen.getByLabelText('Income tax (INR)'), '200000');
    await user.type(screen.getByLabelText('Employer contribution (INR)'), '120000');
    await user.type(screen.getByLabelText(/Bonus per year/), '50000');

    expect(screen.getByText('INR 1,450,000')).toBeInTheDocument();
    expect(screen.getByText('INR 1,250,000')).toBeInTheDocument();
    expect(screen.getByText('INR 1,570,000')).toBeInTheDocument();
  });

  it('sends the lines in component order, leaving out the blank ones and the blank dates', async () => {
    const user = userEvent.setup();
    const sent: unknown[] = [];
    server.use(
      http.post('/api/v1/employees/', async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json({ id: 5, warnings: [] }, { status: 201 });
      }),
    );
    const { router } = renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    await fillIdentity(user);
    await user.type(await screen.findByLabelText('Income tax (INR)'), '90000');
    await user.type(screen.getByLabelText(/Base salary \(INR\)/), '900000');

    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/employees/5'));
    expect(sent).toEqual([
      {
        full_name: 'Meera Iyer',
        email: 'meera@acme.example',
        gender: 'female',
        department: 'engineering',
        designation: 'Engineer',
        level: 2,
        country_code: 'IN',
        joining_date: '2026-11-01',
        note: '',
        lines: [
          { component: 'BASE', annual_amount: '900000' },
          { component: 'TAX', annual_amount: '90000' },
        ],
      },
    ]);
  });

  it("puts the server's field errors on their inputs, by key, by component and by line index", async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/employees/', () =>
        HttpResponse.json(
          {
            email: ['email already belongs to ACME-1'],
            BASE: ['BASE must be at least 10.00, got 0.00'],
            lines: {
              '1': { annual_amount: ['Ensure that there are no more than 2 decimal places.'] },
            },
          },
          { status: 400 },
        ),
      ),
    );
    renderWithProviders(<EmployeeForm />, { route: '/employees/new' });
    await fillIdentity(user);
    await user.type(await screen.findByLabelText(/Base salary \(INR\)/), '0');
    await user.type(screen.getByLabelText('House rent allowance (INR)'), '360000');

    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    expect(await screen.findAllByText('email already belongs to ACME-1')).not.toHaveLength(0);
    expect(screen.getByLabelText(/Email/)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText(/Email/)).toHaveAccessibleDescription(
      'email already belongs to ACME-1',
    );
    expect(screen.getByLabelText(/Base salary \(INR\)/)).toHaveAccessibleDescription(
      'BASE must be at least 10.00, got 0.00',
    );
    expect(screen.getByLabelText('House rent allowance (INR)')).toHaveAccessibleDescription(
      'Ensure that there are no more than 2 decimal places.',
    );
    const summary = screen.getByRole('alert');
    expect(
      within(summary).getByRole('link', { name: 'BASE must be at least 10.00, got 0.00' }),
    ).toBeInTheDocument();
  });
});
