import type { FormEvent } from 'react';

/** A Dialog's `slotProps.paper` that makes the paper itself the form, so DialogContent scrolls
 * between a fixed title and actions (MUI's paper is the flex column). `noValidate` leaves the
 * checks to zod; PaperProps does not declare it, so the props are built here, not inline. */
export function formPaper(onSubmit: (event?: FormEvent) => unknown) {
  return { component: 'form' as const, onSubmit, noValidate: true };
}
