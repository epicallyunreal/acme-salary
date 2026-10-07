import type { Country, Department } from '../../api/types';

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
