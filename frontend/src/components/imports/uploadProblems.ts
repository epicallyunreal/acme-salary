import type { ApiError } from '../../api/client';
import type { FormMessage } from '../forms/applyServerErrors';

/** The 400, 413 and other refusals of an upload as one list for the error summary. Every key of
 * the refusal is shown (SPEC F1): what is missing or ambiguous first, then what was ignored. A
 * failure that is not an answer from the API is waited through instead (D72). */
export function uploadProblems(error: ApiError): FormMessage[] {
  const detail = error.detail();
  if (detail) return [{ key: null, message: detail }];
  const fields = error.fieldErrors();
  const order = [
    'file',
    'rows',
    'missing_columns',
    'ambiguous_columns',
    'repeated_columns',
    'unknown_columns',
  ];
  const keys = [...order, ...Object.keys(fields).filter((key) => !order.includes(key))];
  const problems = keys.flatMap((key) =>
    (fields[key] ?? []).map((message) => ({ key: null, message })),
  );
  return problems.length
    ? problems
    : [{ key: null, message: `The file was refused (error ${error.status}).` }];
}
