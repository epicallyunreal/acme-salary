import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw/http';
import { describe, expect, it } from 'vitest';

import { getRefreshToken, setSession } from '../lib/auth';
import { HR_EMAIL, HR_PASSWORD } from '../test/handlers';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

async function signIn(password = HR_PASSWORD) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Email'), HR_EMAIL);
  await user.type(screen.getByLabelText('Password'), password);
  await user.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('Login', () => {
  it('signs in and returns to the page the user wanted', async () => {
    const { router } = renderApp('/login?next=%2Femployees%3Fpage%3D2');

    await signIn();

    await screen.findByRole('heading', { name: 'Employees' });
    const { pathname, search } = router.state.location;
    expect(`${pathname}${search}`).toBe('/employees?page=2');
    expect(getRefreshToken()).toBe('refresh-1');
    expect(await screen.findByText(HR_EMAIL)).toBeInTheDocument();
  });

  it('goes to the start page without a next', async () => {
    const { router } = renderApp('/login');

    await signIn();

    await screen.findByRole('heading', { name: 'Employees' });
    expect(router.state.location.pathname).toBe('/employees');
  });

  it('says when the email or password is wrong', async () => {
    renderApp('/login');

    await signIn('wrong');

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is wrong.');
    expect(getRefreshToken()).toBeNull();
  });

  it('says to wait when the login is throttled', async () => {
    server.use(
      http.post('/api/v1/auth/login/', () =>
        HttpResponse.json({ detail: 'Request was throttled.' }, { status: 429 }),
      ),
    );
    renderApp('/login');

    await signIn();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many attempts. Wait a minute and try again.',
    );
  });

  it('asks for both fields before sending anything', async () => {
    renderApp('/login');
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Enter your email address')).toBeInTheDocument();
    expect(screen.getByText('Enter your password')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('sends a signed-in visitor straight to the app', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/login');

    await screen.findByRole('heading', { name: 'Employees' });
  });
});
