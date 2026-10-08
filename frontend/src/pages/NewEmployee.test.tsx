import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { beforeEach, describe, expect, it } from 'vitest';

import { setSession } from '../lib/auth';
import { employeeDetails } from '../test/fixtures/detail';
import { countries } from '../test/fixtures/meta';
import { renderApp } from '../test/render';
import { server } from '../test/setup';
import { expectEveryFieldLabelled } from '../test/a11y';

describe('NewEmployee', () => {
  beforeEach(() => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
  });

  it('opens from the directory', async () => {
    const user = userEvent.setup();
    renderApp('/employees');

    await user.click(await screen.findByRole('link', { name: 'Add employee' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'New employee' }),
    ).toBeInTheDocument();
  });

  it('saves the employee and opens their page with what was saved', async () => {
    const user = userEvent.setup();
    const meera = {
      ...employeeDetails[1],
      id: 5,
      employee_code: 'ACME-5',
      full_name: 'Meera Iyer',
    };
    server.use(
      http.post('/api/v1/employees/', () =>
        HttpResponse.json(
          {
            ...meera,
            warnings: [
              {
                field: 'gross',
                severity: 'warning',
                message: 'gross 300,000 INR is below the India minimum 400,000',
              },
            ],
          },
          { status: 201 },
        ),
      ),
      http.get('/api/v1/employees/5/', () => HttpResponse.json(meera)),
      http.get('/api/v1/employees/5/compensation/', () => HttpResponse.json([])),
    );
    renderApp('/employees/new');

    await user.type(await screen.findByLabelText(/Full name/), 'Meera Iyer');
    await user.type(screen.getByLabelText(/Email/), 'meera@acme.example');
    await user.selectOptions(screen.getByLabelText(/Gender/), 'female');
    await screen.findByRole('option', { name: 'India (INR)' });
    await user.selectOptions(screen.getByLabelText(/Country/), 'IN');
    await screen.findByRole('option', { name: 'Engineering' });
    await user.selectOptions(screen.getByLabelText(/Department/), 'engineering');
    await user.type(screen.getByLabelText(/Designation/), 'Engineer');
    await user.selectOptions(screen.getByLabelText(/Level/), '2');
    fireEvent.change(screen.getByLabelText(/Joining date/), { target: { value: '2026-11-01' } });
    await user.type(await screen.findByLabelText(/Base salary \(INR\)/), '300000');
    await user.click(screen.getByRole('button', { name: 'Save employee' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Meera Iyer' }),
    ).toBeInTheDocument();
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Meera Iyer added as ACME-5. Check it: gross 300,000 INR is below the India minimum 400,000.',
    );
  });
  it('says so when the countries and departments do not load, and the retry loads them', async () => {
    const user = userEvent.setup();
    let failing = true;
    server.use(
      http.get('/api/v1/meta/countries/', () =>
        failing ? HttpResponse.json({}, { status: 500 }) : HttpResponse.json(countries),
      ),
    );
    renderApp('/employees/new');

    expect(
      await screen.findByText(
        'Could not load the countries and departments. Check your connection and try again.',
      ),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() =>
      expect(screen.queryByText(/Could not load the countries/)).not.toBeInTheDocument(),
    );
  });

  it('labels every field of the form', async () => {
    renderApp('/employees/new');
    await screen.findByRole('heading', { level: 1, name: 'New employee' });
    await screen.findByLabelText(/Full name/);

    expectEveryFieldLabelled();
  });
});
