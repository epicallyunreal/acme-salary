// Puts a failed request's messages onto a react-hook-form form (DESIGN section 6). In order: a
// key that is a component code of the form's country lands on `lines.<code>`; DRF's per-item
// `lines` errors land on the line sent at that index, and a plain string among them is
// form-level; a key that is a form field lands on that field; `detail`, `non_field_errors` and
// every other key go to one form-level list, each message with its key, so nothing is dropped.
// DRF 3.18 sends per-item errors as an object keyed by index rather than a list; both are read
// the same way (D46).

import type { FieldValues, Path, UseFormSetError } from 'react-hook-form';

import { ApiError } from '../../api/client';

export interface FormMessage {
  /** The key the server used, or null when the failure had no body to read. */
  key: string | null;
  message: string;
}

export interface ErrorTargets<F extends FieldValues> {
  /** The fields the form renders. */
  fields: readonly Path<F>[];
  /** The component codes of the form's country. */
  componentCodes?: readonly string[];
  /** The component codes in the order the request sent its lines. */
  sentLineCodes?: readonly string[];
}

const OFFLINE = 'Could not save. Check your connection and try again.';
const UNREADABLE = 'Could not save. Try again in a moment.';

function messagesOf(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(messagesOf);
  if (value && typeof value === 'object') return Object.values(value).flatMap(messagesOf);
  return [];
}

/** Sets the field errors it can place and returns the form-level messages it could not. */
export function applyServerErrors<F extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<F>,
  { fields, componentCodes = [], sentLineCodes = [] }: ErrorTargets<F>,
): FormMessage[] {
  if (!(error instanceof ApiError)) return [{ key: null, message: OFFLINE }];
  const body = error.data;
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return [{ key: null, message: UNREADABLE }];
  }

  const formLevel: FormMessage[] = [];
  const toForm = (key: string, messages: string[]) =>
    messages.forEach((message) => formLevel.push({ key, message }));
  const toField = (name: string, messages: string[]) => {
    if (messages.length) setError(name as Path<F>, { type: 'server', message: messages.join(' ') });
  };

  for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
    if (key === 'lines' && value && typeof value === 'object') {
      const items: [string, unknown][] = Array.isArray(value)
        ? value.map((item, index) => [String(index), item])
        : Object.entries(value);
      for (const [index, item] of items) {
        const code = /^\d+$/.test(index) ? sentLineCodes[Number(index)] : undefined;
        if (typeof item === 'string' || !code) toForm('lines', messagesOf(item));
        else toField(`lines.${code}`, messagesOf(item));
      }
    } else if (componentCodes.includes(key)) {
      toField(`lines.${key}`, messagesOf(value));
    } else if ((fields as readonly string[]).includes(key)) {
      toField(key, messagesOf(value));
    } else {
      toForm(key, messagesOf(value));
    }
  }
  return formLevel;
}
