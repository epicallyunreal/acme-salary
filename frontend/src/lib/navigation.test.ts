import { describe, expect, it } from 'vitest';

import { loginPath, safeNext } from './navigation';

describe('loginPath', () => {
  it('carries the current page as next, except for the start page', () => {
    expect(loginPath({ pathname: '/', search: '' })).toBe('/login');
    expect(loginPath({ pathname: '/employees', search: '?page=2' })).toBe(
      '/login?next=%2Femployees%3Fpage%3D2',
    );
  });
});

describe('loginPath on the login page', () => {
  it('keeps the next it already has instead of nesting', () => {
    expect(loginPath({ pathname: '/login', search: '?next=%2Femployees' })).toBe(
      '/login?next=%2Femployees',
    );
  });
});

describe('safeNext', () => {
  it('only follows a same-origin path', () => {
    expect(safeNext('/employees?page=2')).toBe('/employees?page=2');
    expect(safeNext('/employees?page=2#top')).toBe('/employees?page=2#top');
    expect(safeNext('//evil.example/phish')).toBe('/');
    expect(safeNext('https://evil.example')).toBe('/');
    expect(safeNext(null)).toBe('/');
    expect(safeNext('')).toBe('/');
  });

  it('sends a dot segment that leaves the path starting with // to the start page', () => {
    // The parser drops the segment and keeps the host, leaving //evil.example/phish (D73).
    for (const next of [
      '/.//evil.example/phish',
      '/..//evil.example/phish',
      '/%2e//evil.example/phish',
    ]) {
      expect(safeNext(next)).toBe('/');
    }
  });

  it('is not fooled by characters the URL parser strips or rewrites', () => {
    expect(safeNext('/\\evil.example')).toBe('/');
    expect(safeNext('/\t/evil.example')).toBe('/');
    expect(safeNext('/\n/evil.example')).toBe('/');
    expect(safeNext('/\\/evil.example')).toBe('/');
  });
});
