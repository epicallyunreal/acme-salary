import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ErrorSummary } from './ErrorSummary';

const PROBLEM = [{ inputId: 'full_name', message: 'Enter the full name' }];

describe('ErrorSummary', () => {
  it('takes focus when the problems of a failed submit arrive a render after its attempt', () => {
    // A form's first invalid submit can count the attempt before its errors are in.
    const { rerender } = render(<ErrorSummary title="The employee was not saved" attempt={1} />);
    rerender(<ErrorSummary title="The employee was not saved" fields={PROBLEM} attempt={1} />);

    expect(screen.getByRole('alert')).toHaveFocus();
  });

  it('takes focus once per attempt, never again while the same problems stay on screen', () => {
    const { rerender } = render(
      <ErrorSummary title="The employee was not saved" fields={PROBLEM} attempt={1} />,
    );
    const field = document.createElement('input');
    document.body.append(field);
    field.focus();

    rerender(<ErrorSummary title="The employee was not saved" fields={PROBLEM} attempt={1} />);

    expect(field).toHaveFocus();
    field.remove();
  });
});
