import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../lib/auth';
import { employeeDetails, histories } from '../test/fixtures/detail';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

async function openExitDialog() {
  const user = userEvent.setup();
  renderApp('/employees/1');
  await user.click(await screen.findByRole('button', { name: 'Mark exited' }));
  const dialog = await screen.findByRole('dialog', { name: 'Mark Asha Rao exited' });
  fireEvent.change(within(dialog).getByLabelText(/Last working day/), {
    target: { value: '2026-09-30' },
  });
  return { user, dialog };
}

describe('EmployeeDetail', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('shows who the employee is and the record in force, in both currencies', async () => {
    renderApp('/employees/1');

    expect(await screen.findByRole('heading', { level: 1, name: 'Asha Rao' })).toBeInTheDocument();
    expect(screen.getByText('ACME-1')).toBeInTheDocument();
    expect(screen.getByText('HR-58213')).toBeInTheDocument();
    expect(screen.getByText('Senior Engineer')).toBeInTheDocument();
    const card = screen.getByRole('region', { name: 'Current record' });
    expect(within(card).getByText('1,450,000')).toBeInTheDocument();
    expect(within(card).getByText('USD 17,400')).toBeInTheDocument();
    expect(within(card).getByText('INR 120,833 a month')).toBeInTheDocument();
    expect(await within(card).findByText('House rent allowance')).toBeInTheDocument();
    const bonus = within(card).getByRole('row', { name: /Bonus/ });
    expect(within(bonus).getByText('50,000.00')).toBeInTheDocument();
    expect(within(card).getByText('October 2026 rate: 1 INR = 0.012 USD')).toBeInTheDocument();
  });

  it('labels the latest record of an exited employee and offers no exit', async () => {
    renderApp('/employees/3');

    const card = await screen.findByRole('region', { name: 'Latest record' });
    expect(within(card).getByText('exited 30 Jun 2026')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark exited' })).not.toBeInTheDocument();
  });

  it('lists history newest first, greys the cancelled row, and offers Cancel only when scheduled', async () => {
    renderApp('/employees/4');

    const table = await screen.findByRole('table', { name: 'Pay history' });
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map((row) => row.getAttribute('data-state'))).toEqual([
      'scheduled',
      'cancelled',
      'current',
    ]);
    expect(within(rows[0]).getByText('v3')).toBeInTheDocument();
    expect(within(rows[1]).getByText('cancelled')).toBeInTheDocument();
    expect(
      within(rows[1]).getByText('Cancelled 5 Oct 2026 by hr@acme.example'),
    ).toBeInTheDocument();
    expect(within(rows[2]).getByText('1 Sept 2023 to 31 Oct 2026')).toBeInTheDocument();
    expect(within(table).getAllByRole('button')).toHaveLength(1);
    expect(within(rows[0]).getByRole('button', { name: 'Cancel revision v3' })).toBeInTheDocument();
  });

  it('cancels a scheduled revision after confirming, then says so', async () => {
    const user = userEvent.setup();
    const deleted: string[] = [];
    server.use(
      http.delete('/api/v1/compensation/:id/', ({ params }) => {
        deleted.push(String(params.id));
        return HttpResponse.json({});
      }),
    );
    renderApp('/employees/4');

    await user.click(await screen.findByRole('button', { name: 'Cancel revision v3' }));
    const dialog = await screen.findByRole('dialog', { name: 'Cancel revision v3?' });
    await user.click(within(dialog).getByRole('button', { name: 'Cancel revision' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Revision v3 cancelled.');
    expect(deleted).toEqual(['43']);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows a 409 from the exit inline, and puts a 400 on the date field', async () => {
    server.use(
      http.post('/api/v1/employees/:id/exit/', () =>
        HttpResponse.json(
          { detail: 'scheduled revision on 2027-04-01 must be cancelled before exit' },
          { status: 409 },
        ),
      ),
    );
    const { user, dialog } = await openExitDialog();

    await user.click(within(dialog).getByRole('button', { name: 'Mark exited' }));

    expect(
      await within(dialog).findByText(
        'scheduled revision on 2027-04-01 must be cancelled before exit',
      ),
    ).toBeInTheDocument();
    expect(within(dialog).getByText('detail')).toBeInTheDocument();

    server.use(
      http.post('/api/v1/employees/:id/exit/', () =>
        HttpResponse.json({ last_date: ['last_date precedes joining_date'] }, { status: 400 }),
      ),
    );
    await user.click(within(dialog).getByRole('button', { name: 'Mark exited' }));

    expect(await within(dialog).findByText('last_date precedes joining_date')).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/Last working day/)).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  });

  it('asks for a date before sending the exit', async () => {
    const user = userEvent.setup();
    renderApp('/employees/1');
    await user.click(await screen.findByRole('button', { name: 'Mark exited' }));
    const dialog = await screen.findByRole('dialog', { name: 'Mark Asha Rao exited' });

    await user.click(within(dialog).getByRole('button', { name: 'Mark exited' }));

    expect(await within(dialog).findByText('Enter the last working day')).toBeInTheDocument();
  });

  it('marks an employee exited and says so', async () => {
    const { user, dialog } = await openExitDialog();

    await user.click(within(dialog).getByRole('button', { name: 'Mark exited' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Asha Rao marked exited, last day 30 Sept 2026.',
    );
  });

  it('lists who changed what, and when, in the audit tab', async () => {
    const user = userEvent.setup();
    renderApp('/employees/1');

    await user.click(await screen.findByRole('tab', { name: 'Audit' }));

    const table = await screen.findByRole('table', { name: 'Audit list' });
    const [update, create, first] = within(table).getAllByRole('row').slice(1);
    expect(within(update).getByText('hr@acme.example')).toBeInTheDocument();
    expect(
      within(update).getByText('Designation: Engineer to Senior Engineer'),
    ).toBeInTheDocument();
    expect(within(update).getByText('Level: 2 to 3')).toBeInTheDocument();
    expect(within(create).getByText('System')).toBeInTheDocument();
    expect(within(create).getByText('Created ACME-1')).toBeInTheDocument();
    expect(
      within(first).getByText('First pay record v1 from 1 Jan 2020, gross INR 1,450,000'),
    ).toBeInTheDocument();
  });

  it('says an unknown employee does not exist', async () => {
    renderApp('/employees/999');

    expect(
      await screen.findByText('This employee does not exist. Go back to the directory.'),
    ).toBeInTheDocument();
  });

  it('offers a retry when the employee does not load', async () => {
    server.use(http.get('/api/v1/employees/:id/', () => HttpResponse.json({}, { status: 500 })));
    renderApp('/employees/1');

    expect(
      await screen.findByText('Could not load this employee. Check your connection and try again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
  it('adds a revision that starts from the latest amounts, then says so', async () => {
    const user = userEvent.setup();
    const sent: unknown[] = [];
    server.use(
      http.post('/api/v1/employees/:id/compensation/', async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(
          { ...histories[1][0], id: 12, version: 2, warnings: [] },
          { status: 201 },
        );
      }),
    );
    renderApp('/employees/1');

    await user.click(await screen.findByRole('button', { name: 'Add revision' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a revision for Asha Rao' });
    const base = await within(dialog).findByLabelText('Base salary (INR)');
    expect(base).toHaveValue('1000000.00');
    fireEvent.change(within(dialog).getByLabelText(/Effective from/), {
      target: { value: '2026-11-01' },
    });
    await user.clear(base);
    await user.type(base, '1100000');
    await user.click(within(dialog).getByRole('button', { name: 'Save revision' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Revision v2 saved.');
    expect(sent).toEqual([
      {
        effective_from: '2026-11-01',
        note: '',
        bonus_annual: '50000.00',
        lines: [
          { component: 'BASE', annual_amount: '1100000' },
          { component: 'HRA', annual_amount: '400000.00' },
          { component: 'TAX', annual_amount: '200000.00' },
          { component: 'EMPLOYER_CONTRIBUTION', annual_amount: '120000.00' },
        ],
      },
    ]);
  });

  it("puts a revision's date error on the date field", async () => {
    const user = userEvent.setup();
    server.use(
      http.post('/api/v1/employees/:id/compensation/', () =>
        HttpResponse.json(
          { effective_from: ['effective_from must be after 2020-01-01 (latest record)'] },
          { status: 400 },
        ),
      ),
    );
    renderApp('/employees/1');
    await user.click(await screen.findByRole('button', { name: 'Add revision' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a revision for Asha Rao' });
    await within(dialog).findByLabelText('Base salary (INR)');
    fireEvent.change(within(dialog).getByLabelText(/Effective from/), {
      target: { value: '2020-01-01' },
    });

    await user.click(within(dialog).getByRole('button', { name: 'Save revision' }));

    expect(await within(dialog).findByLabelText(/Effective from/)).toHaveAccessibleDescription(
      'effective_from must be after 2020-01-01 (latest record)',
    );
  });

  it('sends only the identity fields that changed, then says so', async () => {
    const user = userEvent.setup();
    const sent: unknown[] = [];
    server.use(
      http.patch('/api/v1/employees/:id/', async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(employeeDetails[1]);
      }),
    );
    renderApp('/employees/1');

    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Asha Rao' });
    const designation = within(dialog).getByLabelText(/Designation/);
    await user.clear(designation);
    await user.type(designation, 'Staff Engineer');
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Changes saved.');
    expect(sent).toEqual([{ designation: 'Staff Engineer' }]);
    // The codes are never the client's to send (D48).
    expect(sent[0]).not.toHaveProperty('employee_code');
    expect(sent[0]).not.toHaveProperty('legacy_code');
  });

  it('closes the edit without a request when nothing changed', async () => {
    const user = userEvent.setup();
    const sent: unknown[] = [];
    server.use(
      http.patch('/api/v1/employees/:id/', async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(employeeDetails[1]);
      }),
    );
    renderApp('/employees/1');

    await user.click(await screen.findByRole('button', { name: 'Edit' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Asha Rao' });
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sent).toEqual([]);
  });
});
