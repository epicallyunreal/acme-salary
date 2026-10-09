import { describe, expect, it } from 'vitest';

import html from '../index.html?raw';

// The files the build copies to the site root, by their paths.
const PUBLIC = Object.keys(import.meta.glob('../public/*'));

/** The page every route is served from, parsed as the browser reads it. */
function indexHtml(): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

describe('index.html', () => {
  it("links ACME's own icons, so every route and the login share them (D80)", () => {
    const head = indexHtml().head;

    expect(head.querySelector('link[rel="icon"][type="image/svg+xml"]')?.getAttribute('href')).toBe(
      '/favicon.svg',
    );
    expect(head.querySelector('link[rel="icon"][sizes="32x32"]')?.getAttribute('href')).toBe(
      '/favicon.ico',
    );
    expect(head.querySelector('link[rel="apple-touch-icon"]')?.getAttribute('href')).toBe(
      '/apple-touch-icon.png',
    );
  });

  it('ships each icon it links from public/, so the build copies them to the site root', () => {
    for (const name of ['favicon.svg', 'favicon.ico', 'apple-touch-icon.png']) {
      expect(PUBLIC).toContain(`../public/${name}`);
    }
  });
});
