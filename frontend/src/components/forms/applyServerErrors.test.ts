import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import { applyServerErrors } from './applyServerErrors';

type Form = {
  effective_from: string;
  bonus_annual: string;
  lines: Record<string, string>;
};

const TARGETS = {
  fields: ['effective_from', 'bonus_annual'] as const,
  componentCodes: ['BASE', 'HRA', 'ALLOWANCES', 'TAX', 'EMPLOYER_CONTRIBUTION'],
  sentLineCodes: ['BASE', 'HRA', 'TAX'],
};

function apply(data: unknown, status = 400) {
  const setError = vi.fn();
  const formLevel = applyServerErrors<Form>(new ApiError(status, data), setError, TARGETS);
  const onFields = Object.fromEntries(
    setError.mock.calls.map(([name, { message }]) => [name, message]),
  );
  return { onFields, formLevel };
}

describe('applyServerErrors', () => {
  it('puts a form field key on that field', () => {
    const { onFields, formLevel } = apply({
      effective_from: ['effective_from must be after 2025-04-01 (latest record)'],
    });

    expect(onFields).toEqual({
      effective_from: 'effective_from must be after 2025-04-01 (latest record)',
    });
    expect(formLevel).toEqual([]);
  });

  it("puts a component code of the form's country on its line", () => {
    const { onFields } = apply({
      BASE: ['BASE is required'],
      HRA: ['HRA must be a non-negative number, got -5'],
    });

    expect(onFields).toEqual({
      'lines.BASE': 'BASE is required',
      'lines.HRA': 'HRA must be a non-negative number, got -5',
    });
  });

  it('maps a per-item lines error to the line sent at that index, as a list or keyed by index', () => {
    const message = 'Ensure that there are no more than 2 decimal places.';

    const asList = apply({ lines: [{}, { annual_amount: [message] }, {}] });
    const asObject = apply({ lines: { '2': { annual_amount: [message] } } });

    expect(asList.onFields).toEqual({ 'lines.HRA': message });
    expect(asObject.onFields).toEqual({ 'lines.TAX': message });
  });

  it('keeps a plain string under lines at form level', () => {
    const { onFields, formLevel } = apply({ lines: ['BASE appears twice in lines'] });

    expect(onFields).toEqual({});
    expect(formLevel).toEqual([{ key: 'lines', message: 'BASE appears twice in lines' }]);
  });

  it('shows a detail alone, as a form-level alert (DESIGN section 6, found in the pass)', () => {
    const { onFields, formLevel } = apply(
      { detail: 'no revision after the exit on 2026-06-30' },
      409,
    );

    expect(onFields).toEqual({});
    expect(formLevel).toEqual([{ key: null, message: 'no revision after the exit on 2026-06-30' }]);
  });

  it('shows each non_field_errors message alone', () => {
    const { onFields, formLevel } = apply({ non_field_errors: ['first', 'second'] });

    expect(onFields).toEqual({});
    expect(formLevel).toEqual([
      { key: null, message: 'first' },
      { key: null, message: 'second' },
    ]);
  });

  it('keeps the key of a field the form cannot place, dropping nothing', () => {
    const { onFields, formLevel } = apply({ CPF: ['CPF is not a component for IN'] });

    expect(onFields).toEqual({});
    expect(formLevel).toEqual([{ key: 'CPF', message: 'CPF is not a component for IN' }]);
  });

  it('says what to do when there is no body to read', () => {
    const setError = vi.fn();

    expect(applyServerErrors<Form>(new TypeError('Failed to fetch'), setError, TARGETS)).toEqual([
      { key: null, message: 'Could not save. Check your connection and try again.' },
    ]);
    expect(applyServerErrors<Form>(new ApiError(502, 'Bad gateway'), setError, TARGETS)).toEqual([
      { key: null, message: 'Could not save. Try again in a moment.' },
    ]);
    expect(setError).not.toHaveBeenCalled();
  });
});
