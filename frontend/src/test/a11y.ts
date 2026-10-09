import { screen, waitFor } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { expect } from 'vitest';

/** Every input in `scope` has an accessible name (SPEC section 13, accessibility): the ones with
 * an ARIA role, and the password, date and file inputs, which have none. */
export function expectEveryFieldLabelled(scope: HTMLElement = document.body) {
  const fields = Array.from(
    scope.querySelectorAll<HTMLElement>('input:not([type=hidden]), select, textarea'),
  ).filter((field) => field.closest('[aria-hidden="true"]') === null);
  expect(fields.length).toBeGreaterThan(0);
  for (const field of fields) expect(field).toHaveAccessibleName();
}

/** Opening a dialog from `trigger` with the keyboard moves focus into it, and closing it with
 * Escape hands focus back to the trigger (DESIGN section 6, keyboard). `whileOpen` runs against
 * the open dialog, for checks that need its fields on screen. */
export async function expectFocusCycle(
  user: UserEvent,
  trigger: HTMLElement,
  dialogName: string,
  whileOpen?: (dialog: HTMLElement) => void,
) {
  trigger.focus();
  await user.keyboard('{Enter}');
  const dialog = await screen.findByRole('dialog', { name: dialogName });
  await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement));
  whileOpen?.(dialog);
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog', { name: dialogName })).toBeNull());
  expect(trigger).toHaveFocus();
  return dialog;
}
