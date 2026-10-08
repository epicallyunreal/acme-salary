import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { expect, vi } from 'vitest';

/** A handler that answers only once `release` is called, so the pending dialog can be looked at. */
export function held<T>(answer: () => T): { handler: () => Promise<T>; release: () => void } {
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  return {
    handler: async () => {
      await gate;
      return answer();
    },
    release,
  };
}

/** Holds one request at the fetch itself, answering it with `respond` once `release` is called,
 * for a multipart upload: jsdom closes a file body that an MSW handler keeps waiting on. Every
 * other request goes through as usual. */
export function holdFetch(
  matches: (method: string, url: string) => boolean,
  respond: () => Response,
): () => void {
  const realFetch = globalThis.fetch;
  let release = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? (input instanceof Request ? input.method : 'GET');
    if (!matches(method, url)) return realFetch(input, init);
    await gate;
    return respond();
  });
  return release;
}

/** A click on the topmost dialog's backdrop, the way MUI tells one from a click in the paper. */
export function clickBackdrop() {
  const containers = document.querySelectorAll('.MuiDialog-container');
  const container = containers[containers.length - 1];
  if (!container) throw new Error('no dialog is open');
  fireEvent.mouseDown(container);
  fireEvent.click(container);
}

/** The busy dialog named `title`, pending: no button, and neither Escape nor the backdrop
 * closes it (D72). */
export async function expectPending(title: string): Promise<HTMLElement> {
  const dialog = await screen.findByRole('dialog', { name: title });
  expect(within(dialog).queryByRole('button')).not.toBeInTheDocument();
  fireEvent.keyDown(dialog, { key: 'Escape' });
  clickBackdrop();
  expect(screen.getByRole('dialog', { name: title })).toBeInTheDocument();
  return dialog;
}

export async function expectClosed(title: string) {
  await waitFor(
    () => expect(screen.queryByRole('dialog', { name: title })).not.toBeInTheDocument(),
    { timeout: 4000 },
  );
}

/** The busy dialog turned into the failure named `title`, saying `message`, closed by its Close
 * button, the one way to dismiss it. */
export async function expectFailed(title: string, message: string) {
  const dialog = await screen.findByRole('dialog', { name: title });
  expect(within(dialog).getByRole('alert')).toHaveTextContent(message);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
  await expectClosed(title);
}
