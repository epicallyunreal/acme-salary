// Hand-written mirrors of the serializer shapes (SPEC section 8, DESIGN 1.3). Money is a string.

export interface Me {
  id: number;
  email: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Country {
  code: string;
  name: string;
  currency_code: string;
  min_gross_annual?: string;
}

export interface Department {
  id?: number;
  code: string;
  name: string;
}

export type EmployeeStatus = 'active' | 'exited' | 'upcoming';
export type ReportingCurrency = 'usd' | 'eur' | 'local';

/** The record the directory shows: current on the reporting date, else the latest with a label. */
export interface ShownRecord {
  record_id: number;
  version: number;
  effective_from: string;
  effective_to: string | null;
  is_current: boolean;
  label: string | null;
  gross_local: string;
  currency_code: string;
  gross_reporting: string;
  reporting_currency: string;
}

export interface EmployeeRow {
  id: number;
  employee_code: string;
  full_name: string;
  email: string;
  department: Pick<Department, 'code' | 'name'>;
  designation: string;
  level: number;
  country: Pick<Country, 'code' | 'name' | 'currency_code'>;
  status: EmployeeStatus;
  joining_date: string;
  last_date: string | null;
  shown: ShownRecord | null;
}

/** The query string of GET /employees/ (SPEC F4). Arrays join with commas on the wire. */
export type ListParams = {
  page?: number;
  page_size?: number;
  ordering?: string;
  search?: string;
  country?: string[];
  department?: string[];
  designation?: string[];
  level?: number[];
  status?: EmployeeStatus;
  gross_min?: string;
  gross_max?: string;
  joined_after?: string;
  joined_before?: string;
  currency?: ReportingCurrency;
};
