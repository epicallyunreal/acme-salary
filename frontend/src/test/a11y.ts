import { screen, waitFor, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { expect } from 'vitest';

const FIELD_ROLES = [
  'textbox',
  'searchbox',
  'combobox',
  'spinbutton',
  'checkbox',
  'radio',
] as const;

/** Every input in `scope` has an accessible name (SPEC section 13, accessibility). */
export function expectEveryFieldLabelled(scope: HTMLElement = document.body) {
  const fields = FIELD_ROLES.flatMap((role) => within(scope).queryAllByRole(role));
  expect(fields.length).toBeGreaterThan(0);
  for (const field of fields) expect(field).toHaveAccessibleName();
}

/** Opening a dialog from `trigger` moves focus into it, and closing it with Escape hands focus
 * back to the trigger (DESIGN section 6, keyboard). */
export async function expectFocusCycle(user: UserEvent, trigger: HTMLElement, dialogName: string) {
  await user.click(trigger);
  const dialog = await screen.findByRole('dialog', { name: dialogName });
  await waitFor(() => expect(dialog).toContainElement(document.activeElement as HTMLElement));
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog', { name: dialogName })).toBeNull());
  expect(trigger).toHaveFocus();
  return dialog;
}
