import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import App from './App';
import { renderWithProviders } from './test/render';

describe('App', () => {
  it('renders the sign-in placeholder with labelled fields', () => {
    renderWithProviders(<App />);

    expect(screen.getByRole('heading', { name: 'ACME Salary' })).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeEnabled();
  });
});
