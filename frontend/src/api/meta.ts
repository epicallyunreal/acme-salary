import { useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys, META_STALE_TIME } from './keys';
import type { Country, Department } from './types';

export function listCountries(): Promise<Country[]> {
  return apiFetch<Country[]>('/meta/countries/');
}

export function listDepartments(): Promise<Department[]> {
  return apiFetch<Department[]>('/meta/departments/');
}

export function useCountries() {
  return useQuery({
    queryKey: keys.meta.countries,
    queryFn: listCountries,
    staleTime: META_STALE_TIME,
  });
}

export function useDepartments() {
  return useQuery({
    queryKey: keys.meta.departments,
    queryFn: listDepartments,
    staleTime: META_STALE_TIME,
  });
}
