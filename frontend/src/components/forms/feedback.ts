// What a form says after a submit: the field problems for its error summary, and the notice a
// successful save leaves behind.

import type { FieldErrors, FieldValues } from 'react-hook-form';

import type { ServerMessage } from '../../api/types';
import type { FieldProblem } from './ErrorSummary';

export interface Notice {
  text: string;
  severity: 'success' | 'warning';
}

/** The save's own words, plus any warning the validators returned beside it (D27). */
export function savedNotice(text: string, warnings: ServerMessage[] = []): Notice {
  if (!warnings.length) return { text, severity: 'success' };
  return {
    text: `${text} Check it: ${warnings.map((warning) => warning.message).join('; ')}.`,
    severity: 'warning',
  };
}

/** The form's errors in the order its fields appear, each linked to its input. */
export function fieldProblems<F extends FieldValues>(
  errors: FieldErrors<F>,
  fields: readonly (readonly [name: string, inputId: string])[],
  lineCodes: readonly string[] = [],
): FieldProblem[] {
  const byName = errors as Record<string, { message?: unknown } | undefined>;
  const problems: FieldProblem[] = [];
  for (const [name, inputId] of fields) {
    const message = byName[name]?.message;
    if (typeof message === 'string' && message) problems.push({ inputId, message });
  }
  const lines = byName.lines as Record<string, { message?: unknown } | undefined> | undefined;
  for (const code of lineCodes) {
    const message = lines?.[code]?.message;
    if (typeof message === 'string' && message) problems.push({ inputId: `line-${code}`, message });
  }
  return problems;
}
