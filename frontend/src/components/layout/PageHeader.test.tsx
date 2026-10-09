import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '../../test/render';
import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('names the page and lets its actions go under the title on a narrow window (D75)', async () => {
    renderWithProviders(
      <PageHeader title="Employees" actions={<button type="button">Add employee</button>} />,
    );

    const heading = await screen.findByRole('heading', { level: 1, name: 'Employees' });
    expect(document.title).toBe('Employees · ACME Salary');
    expect(heading.parentElement?.parentElement).toHaveStyle({
      display: 'flex',
      flexWrap: 'wrap',
    });
  });
});
