// One fetch wrapper for the whole app (DESIGN section 6): prefixes /api/v1, serialises the
// query, carries the bearer token, parses JSON, and turns a 401 into one shared refresh and one
// retry before giving up and sending the user to the login page.

import { apiUrl } from '../lib/constants';
import { clearSession, getAccessToken, refreshOnce } from '../lib/auth';

export type QueryValue =
  string | number | boolean | null | undefined | ReadonlyArray<string | number>;
export type Query = Record<string, QueryValue>;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** The JSON body, or a function that builds it when the request goes out, so the retry after
   * a token refresh sends current values (the logout body carries the refresh token). */
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
}

export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(status: number, data: unknown) {
    super(`API ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }

  /** DRF's 400 shape, `{field: [message, ...]}`, as a plain map; empty for any other body. */
  fieldErrors(): FieldErrors {
    if (!this.data || typeof this.data !== 'object' || Array.isArray(this.data)) return {};
    const errors: FieldErrors = {};
    for (const [field, messages] of Object.entries(this.data as Record<string, unknown>)) {
      if (Array.isArray(messages)) errors[field] = messages.map(String);
      else if (typeof messages === 'string') errors[field] = [messages];
    }
    return errors;
  }

  /** The `detail` of a 401, 404 or 409 body, when there is one. */
  detail(): string | null {
    if (this.data && typeof this.data === 'object' && 'detail' in this.data) {
      const detail = (this.data as { detail: unknown }).detail;
      return typeof detail === 'string' ? detail : null;
    }
    return null;
  }
}

type UnauthenticatedHandler = () => void;
let onUnauthenticated: UnauthenticatedHandler = () => {};

/** The router registers what happens when a request fails twice with 401. */
export function setUnauthenticatedHandler(handler: UnauthenticatedHandler) {
  onUnauthenticated = handler;
}

/** Arrays join with commas (`country=IN,US`), undefined, null and empty values are dropped. */
export function buildQuery(query: Query | undefined): string {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      if (value.length) params.set(key, value.join(','));
    } else {
      params.set(key, String(value));
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers = new Headers();
  const token = getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const payload =
    typeof options.body === 'function' ? (options.body as () => unknown)() : options.body;
  const isForm = typeof FormData !== 'undefined' && payload instanceof FormData;
  let body: BodyInit | undefined;
  if (payload !== undefined) {
    if (isForm) {
      body = payload;
    } else {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(payload);
    }
  }
  return fetch(apiUrl(`${path}${buildQuery(options.query)}`), {
    method: options.method ?? 'GET',
    headers,
    body,
    signal: options.signal,
  });
}

async function parse(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** A request made without a session, such as login, gets no retry; everything else does. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);
  if (response.status === 401 && getAccessToken()) {
    const refreshed = await refreshOnce();
    if (refreshed) {
      response = await send(path, options);
    }
    if (response.status === 401) {
      clearSession();
      onUnauthenticated();
    }
  }
  const data = await parse(response);
  if (!response.ok) throw new ApiError(response.status, data);
  return data as T;
}
