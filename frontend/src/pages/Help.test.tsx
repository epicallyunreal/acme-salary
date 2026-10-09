import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { setSession } from '../lib/auth';
import { renderApp } from '../test/render';
import { server } from '../test/setup';

const ANCHORS = [
  'hidden-figures',
  'currency',
  'include-exited',
  'reporting-start',
  'scheduled-revision',
  'no-deletion',
  'approve-refused',
  'gross-decrease',
  'same-file-twice',
  'long-imports',
  'codes',
  'session',
];

describe('Help', () => {
  it('sits in the nav under the divider, after Demo data, and marks itself current', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/help');

    await screen.findByRole('heading', { level: 1, name: 'Help' });
    const nav = screen.getByRole('navigation', { name: 'Main' });
    const lists = within(nav).getAllByRole('list');
    expect(lists).toHaveLength(2);
    expect(within(nav).getByRole('separator')).toBeInTheDocument();
    expect(
      within(lists[1])
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['Demo data', 'Help']);
    expect(within(nav).getByRole('link', { name: 'Help' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Demo data' })).not.toHaveAttribute(
      'aria-current',
    );
    // The title is set in an effect, after the page shows.
    await waitFor(() => expect(document.title).toBe('Help · ACME Salary'));
  });

  it('gives the six steps in order and every question an anchor, and asks the API nothing', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    const requested: string[] = [];
    const record = ({ request }: { request: Request }) => {
      requested.push(new URL(request.url).pathname);
    };
    server.events.on('request:start', record);
    try {
      renderApp('/help');

      await screen.findByRole('heading', { level: 1, name: 'Help' });
      expect(screen.getByRole('heading', { level: 2, name: 'How it works' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 2, name: 'Questions' })).toBeInTheDocument();
      const howItWorks = screen.getByRole('region', { name: 'How it works' });
      const steps = within(within(howItWorks).getByRole('list'))
        .getAllByRole('listitem')
        .map((item) => within(item).getByRole('heading', { level: 3 }).textContent);
      expect(steps).toEqual(['Import', 'Review', 'Approve', 'Maintain', 'Understand', 'Share']);
      expect(within(howItWorks).getByRole('link', { name: 'Demo data page' })).toHaveAttribute(
        'href',
        '/demo',
      );
      const questions = within(screen.getByRole('region', { name: 'Questions' })).getAllByRole(
        'button',
      );
      expect(questions).toHaveLength(ANCHORS.length);
      for (const id of ANCHORS) {
        expect(document.getElementById(id)).toContainElement(
          document.getElementById(`${id}-question`),
        );
      }
      // Static (D75): the shell asks who is signed in, and the page itself asks nothing.
      await screen.findByText('hr@acme.example');
      expect(requested).toEqual(['/api/v1/auth/me/']);
    } finally {
      server.events.removeListener('request:start', record);
    }
  });

  it('says where the audit trail is and which rates an early period uses (D78)', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    renderApp('/help');
    await screen.findByRole('heading', { level: 1, name: 'Help' });
    const text = document.querySelector('main')?.textContent ?? '';

    expect(text).toContain(
      "Every change is recorded in the employee's audit trail, with who made it and when, on the Audit tab of their page.",
    );
    expect(text).toContain(
      "Rates are kept from September 2026, so a period that ends earlier is converted at September 2026's rates, and the label says so.",
    );
  });

  it('opens the answer an anchor names and brings it into view', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    const scrolled = vi.spyOn(Element.prototype, 'scrollIntoView');
    try {
      renderApp('/help#hidden-figures');

      const question = await screen.findByRole('button', {
        name: 'Why does a figure say "fewer than 5 people" or "fewer than 20 people"?',
      });
      expect(question).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText(/needs at least 5 of each/)).toBeVisible();
      expect(screen.getByRole('button', { name: 'How long does a session last?' })).toHaveAttribute(
        'aria-expanded',
        'false',
      );
      // Brought into view in an effect, after the page shows.
      await waitFor(() =>
        expect(scrolled.mock.contexts).toContain(document.getElementById('hidden-figures')),
      );
    } finally {
      scrolled.mockRestore();
    }
  });

  it('gives the linked question the focus, so the keyboard goes on from the answer', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/help#session');

    const question = await screen.findByRole('button', { name: 'How long does a session last?' });
    await waitFor(() => expect(question).toHaveFocus());
    expect(question).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens the answer a new anchor names while the page is open', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    const { router } = renderApp('/help');
    await screen.findByRole('heading', { level: 1, name: 'Help' });

    await router.navigate('/help#codes');

    // The answers are remounted for the new anchor, so the button is found again each time.
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: 'What is the difference between the ACME code and the legacy code?',
        }),
      ).toHaveAttribute('aria-expanded', 'true'),
    );
  });

  it('shows the page with every answer closed for an anchor that names none, a stray % included', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });

    renderApp('/help#%');

    await screen.findByRole('heading', { level: 1, name: 'Help' });
    expect(
      within(screen.getByRole('region', { name: 'Questions' }))
        .getAllByRole('button')
        .filter((button) => button.getAttribute('aria-expanded') === 'true'),
    ).toEqual([]);
  });

  it('opens any other answer on a click', async () => {
    setSession({ access: 'access-1', refresh: 'refresh-1' });
    renderApp('/help');
    const user = userEvent.setup();
    const question = await screen.findByRole('button', { name: 'How long does a session last?' });

    await user.click(question);

    expect(question).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText(/up to 12 hours from when you sign in/)).toBeVisible();
  });
});
