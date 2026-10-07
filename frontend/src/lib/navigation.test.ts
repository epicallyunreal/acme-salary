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

describe('safeNext', () => {
  it('only follows a same-origin path', () => {
    expect(safeNext('/employees?page=2')).toBe('/employees?page=2');
    expect(safeNext('//evil.example/phish')).toBe('/');
    expect(safeNext('https://evil.example')).toBe('/');
    expect(safeNext(null)).toBe('/');
  });
});
