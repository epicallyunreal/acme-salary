import type { Country, Department, SalaryComponent } from '../../api/types';

/** The ten components of SPEC section 4 rule 2, as seed/profiles.py names them. */
export const components: SalaryComponent[] = [
  { id: 1, code: 'BASE', name: 'Base salary', kind: 'earning', country: null, sort_order: 10 },
  {
    id: 2,
    code: 'HRA',
    name: 'House rent allowance',
    kind: 'earning',
    country: 'IN',
    sort_order: 20,
  },
  { id: 3, code: 'ALLOWANCES', name: 'Allowances', kind: 'earning', country: 'IN', sort_order: 30 },
  {
    id: 4,
    code: 'HOLIDAY_ALLOWANCE',
    name: 'Holiday allowance',
    kind: 'earning',
    country: 'NL',
    sort_order: 20,
  },
  {
    id: 5,
    code: 'AWS',
    name: 'Annual wage supplement',
    kind: 'earning',
    country: 'SG',
    sort_order: 20,
  },
  { id: 6, code: 'TAX', name: 'Income tax', kind: 'deduction', country: null, sort_order: 50 },
  {
    id: 7,
    code: 'NATIONAL_INSURANCE',
    name: 'National Insurance',
    kind: 'deduction',
    country: 'GB',
    sort_order: 60,
  },
  {
    id: 8,
    code: 'SOCIAL_INSURANCE',
    name: 'Social insurance',
    kind: 'deduction',
    country: 'DE',
    sort_order: 60,
  },
  {
    id: 9,
    code: 'CPF',
    name: 'CPF contribution',
    kind: 'deduction',
    country: 'SG',
    sort_order: 60,
  },
  {
    id: 10,
    code: 'EMPLOYER_CONTRIBUTION',
    name: 'Employer contribution',
    kind: 'employer_contribution',
    country: null,
    sort_order: 90,
  },
];

/** GET /meta/components/?country=: the global components plus the country's own, in order. */
export function componentsFor(country: string): SalaryComponent[] {
  return components
    .filter((component) => component.country === null || component.country === country)
    .sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
}

export const countries: Country[] = [
  { code: 'DE', name: 'Germany', currency_code: 'EUR', min_gross_annual: '30000.00' },
  { code: 'GB', name: 'United Kingdom', currency_code: 'GBP', min_gross_annual: '25000.00' },
  { code: 'IN', name: 'India', currency_code: 'INR', min_gross_annual: '300000.00' },
  { code: 'NL', name: 'Netherlands', currency_code: 'EUR', min_gross_annual: '30000.00' },
  { code: 'SG', name: 'Singapore', currency_code: 'SGD', min_gross_annual: '36000.00' },
  { code: 'US', name: 'United States', currency_code: 'USD', min_gross_annual: '35000.00' },
];

export const departments: Department[] = [
  { id: 7, code: 'customer-support', name: 'Customer Support' },
  { id: 4, code: 'data', name: 'Data' },
  { id: 3, code: 'design', name: 'Design' },
  { id: 1, code: 'engineering', name: 'Engineering' },
  { id: 8, code: 'finance', name: 'Finance' },
  { id: 9, code: 'hr', name: 'HR' },
  { id: 11, code: 'it', name: 'IT' },
  { id: 10, code: 'legal', name: 'Legal' },
  { id: 6, code: 'marketing', name: 'Marketing' },
  { id: 12, code: 'operations', name: 'Operations' },
  { id: 2, code: 'product', name: 'Product' },
  { id: 5, code: 'sales', name: 'Sales' },
];
