import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CommitField } from './FilterBar';

describe('CommitField', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('drops its draft and its pending commit when its value changes from outside (D76)', () => {
    const onCommit = vi.fn();
    const field = (value: string) => (
      <CommitField label="Search" value={value} onCommit={onCommit} delay={300} />
    );
    const { rerender } = render(field('asha'));

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'ashar' } });
    rerender(field('ravi'));
    act(() => vi.advanceTimersByTime(300));
    fireEvent.blur(screen.getByLabelText('Search'));

    expect(screen.getByLabelText('Search')).toHaveValue('ravi');
    expect(onCommit).not.toHaveBeenCalled();
  });

  it('keeps its draft through a render that leaves its value alone, and sends it after the pause', () => {
    const onCommit = vi.fn();
    const field = <CommitField label="Search" value="asha" onCommit={onCommit} delay={300} />;
    const { rerender } = render(field);

    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'ashar' } });
    rerender(field);

    expect(screen.getByLabelText('Search')).toHaveValue('ashar');
    act(() => vi.advanceTimersByTime(300));
    expect(onCommit).toHaveBeenCalledExactlyOnceWith('ashar');
  });
});
