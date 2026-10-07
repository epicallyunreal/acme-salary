import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { clearSession, getRefreshToken, setSession, useAccessToken } from '../lib/auth';
import { apiFetch } from './client';
import { keys } from './keys';
import type { Me, TokenPair } from './types';

export interface Credentials {
  email: string;
  password: string;
}

export function login(credentials: Credentials): Promise<TokenPair> {
  return apiFetch<TokenPair>('/auth/login/', { method: 'POST', body: credentials });
}

/** Blacklists whichever refresh token is current when the request goes out, so the retry after
 * a rotation sends the new one rather than the one the rotation just blacklisted. */
export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout/', {
    method: 'POST',
    body: () => ({ refresh: getRefreshToken() }),
  });
}

export function me(): Promise<Me> {
  return apiFetch<Me>('/auth/me/');
}

export function useLogin() {
  return useMutation({
    mutationFn: login,
    onSuccess: (tokens) => setSession(tokens),
  });
}

export function useMe() {
  const token = useAccessToken();
  return useQuery({ queryKey: keys.me, queryFn: me, enabled: token !== null, staleTime: Infinity });
}

/** Posts the refresh token so it is blacklisted, then forgets the session whatever the server said. */
export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      if (getRefreshToken()) {
        try {
          await logout();
        } catch {
          // The token may already be expired or blacklisted; signing out still succeeds locally.
        }
      }
    },
    onSettled: () => {
      clearSession();
      queryClient.clear();
    },
  });
}
