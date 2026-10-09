import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Credit } from './Credit';

describe('Credit', () => {
  it('links to nutanprabhat.dev in a new tab and says so in its name (D80)', () => {
    render(<Credit />);

    const credit = screen.getByRole('link', { name: 'Built by Nutan Prabhat, opens in a new tab' });
    expect(credit).toHaveTextContent('Built by Nutan Prabhat');
    expect(credit).toHaveAttribute('href', 'https://nutanprabhat.dev');
    expect(credit).toHaveAttribute('target', '_blank');
    expect(credit).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
