import { useQuery } from '@tanstack/react-query';

import { apiFetch } from './client';
import { keys, META_STALE_TIME } from './keys';
import type { Country, Department, ExchangeRates, SalaryComponent } from './types';

export function listCountries(): Promise<Country[]> {
  return apiFetch<Country[]>('/meta/countries/');
}

export function listDepartments(): Promise<Department[]> {
  return apiFetch<Department[]>('/meta/departments/');
}

export function getExchangeRates(on?: string): Promise<ExchangeRates> {
  return apiFetch<ExchangeRates>('/meta/exchange-rates/', { query: { on } });
}

/** The rate for every pair in force on `on`, today when not given, with each pair's own date
 * (D28). */
export function useExchangeRates(on?: string) {
  return useQuery({
    queryKey: keys.meta.rates(on),
    queryFn: () => getExchangeRates(on),
    staleTime: META_STALE_TIME,
  });
}

export function listComponents(country: string): Promise<SalaryComponent[]> {
  return apiFetch<SalaryComponent[]>('/meta/components/', { query: { country } });
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

/** The components of one country: names and kinds for the lines the API sends as codes. */
export function useComponents(country: string | undefined) {
  return useQuery({
    queryKey: keys.meta.components(country ?? ''),
    queryFn: () => listComponents(country ?? ''),
    staleTime: META_STALE_TIME,
    enabled: Boolean(country),
  });
}
