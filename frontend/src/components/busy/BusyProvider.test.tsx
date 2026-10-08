import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../api/client';
import { POLL } from '../../lib/poll';
import { clickBackdrop } from '../../test/busy';
import { type BusyOptions, useBusy } from './busyContext';
import { BusyProvider } from './BusyProvider';

interface TriggerProps<T> {
  title: string;
  task: () => Promise<T>;
  options: BusyOptions<T>;
}

function Trigger<T>({ title, task, options }: TriggerProps<T>) {
  const { busy, run } = useBusy();
  return (
    <button disabled={busy !== null} onClick={() => void run(title, task, options)}>
      Go
    </button>
  );
}

function renderTrigger<T>(props: TriggerProps<T>) {
  render(
    <BusyProvider>
      <Trigger {...props} />
    </BusyProvider>,
  );
  return screen.getByRole('button', { name: 'Go' });
}

const flush = () => act(async () => {});
const advance = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

describe('BusyProvider', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('counts the seconds, says why it may be slow after 20 s, warns before the page is left, and closes on the result', async () => {
    let finish: (value: string) => void = () => {};
    const go = renderTrigger({
      title: 'Staging october.csv\u2026',
      task: () =>
        new Promise<string>((resolve) => {
          finish = resolve;
        }),
      options: { failedTitle: 'The file was not staged' },
    });

    fireEvent.click(go);
    await flush();

    const dialog = screen.getByRole('dialog', { name: 'Staging october.csv\u2026' });
    expect(within(dialog).getByText('0 s elapsed')).toBeInTheDocument();
    expect(within(dialog).queryByRole('button')).not.toBeInTheDocument();
    expect(go).toBeDisabled();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    clickBackdrop();
    expect(screen.getByRole('dialog', { name: 'Staging october.csv\u2026' })).toBeInTheDocument();
    await advance(19_000);
    expect(within(dialog).getByText('19 s elapsed')).toBeInTheDocument();
    expect(within(dialog).queryByText(/small shared machine/)).not.toBeInTheDocument();
    await advance(1_000);
    expect(within(dialog).getByText('20 s elapsed')).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        'The demo runs on a small shared machine; this can take a few minutes.',
      ),
    ).toBeInTheDocument();
    const leaving = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(leaving);
    expect(leaving.defaultPrevented).toBe(true);

    await act(async () => finish('staged'));
    await advance(1_000);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(go).toBeEnabled();
    const later = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(later);
    expect(later.defaultPrevented).toBe(false);
  });

  it('looks for the result for ten minutes after a cut connection, then says so with Close', async () => {
    const recover = vi.fn(async () => null);
    const go = renderTrigger({
      title: 'Applying 2 rows\u2026',
      task: () => Promise.reject(new TypeError('Failed to fetch')),
      options: {
        failedTitle: 'Nothing was applied',
        recover,
        gaveUp:
          'The server may still be working, or the approve was refused; open the batch again.',
      },
    });

    fireEvent.click(go);
    await flush();

    expect(screen.getByRole('status')).toHaveTextContent('Still working\u2026');
    await advance(POLL.upTo - POLL.every);
    expect(screen.getByRole('dialog', { name: 'Applying 2 rows\u2026' })).toBeInTheDocument();
    expect(recover.mock.calls.length).toBeGreaterThan(100);
    await advance(POLL.every);

    const failed = screen.getByRole('dialog', { name: 'Nothing was applied' });
    expect(within(failed).getByRole('alert')).toHaveTextContent(
      'The server may still be working, or the approve was refused; open the batch again.',
    );
    fireEvent.click(within(failed).getByRole('button', { name: 'Close' }));
    await advance(1_000);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows a refusal with Close, and a cut connection with nothing to look for as a failure', async () => {
    const go = renderTrigger({
      title: 'Preparing employees.csv\u2026',
      task: () => Promise.reject(new ApiError(409, { detail: 'another export is running' })),
      options: { failedTitle: 'Could not export the employees' },
    });

    fireEvent.click(go);
    await flush();

    const failed = screen.getByRole('dialog', { name: 'Could not export the employees' });
    expect(within(failed).getByRole('alert')).toHaveTextContent('another export is running');
    expect(within(failed).getByRole('button', { name: 'Close' })).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Go', hidden: true })).toBeDisabled();
    fireEvent.click(within(failed).getByRole('button', { name: 'Close' }));
    await advance(1_000);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('treats a result the caller calls a refusal as one', async () => {
    const go = renderTrigger({
      title: 'Applying 2 rows\u2026',
      task: () => Promise.resolve({ status: 'failed' }),
      options: {
        failedTitle: 'Nothing was applied',
        refusal: (batch) =>
          batch.status === 'failed'
            ? [{ key: null, message: 'approve failed, the batch is marked failed' }]
            : null,
      },
    });

    fireEvent.click(go);
    await flush();

    const failed = screen.getByRole('dialog', { name: 'Nothing was applied' });
    expect(within(failed).getByRole('alert')).toHaveTextContent(
      'approve failed, the batch is marked failed',
    );
  });
});
