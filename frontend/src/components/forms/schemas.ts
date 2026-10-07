// zod schemas that mirror the input serializers (DESIGN section 6). Dates and amounts stay
// strings, so no float arithmetic happens in the browser; the server runs the business rules
// and its messages land on the same fields through applyServerErrors.

import { z } from 'zod';

import { GENDERS } from '../../lib/constants';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const AMOUNT = /^\d+(\.\d{1,2})?$/;
const AMOUNT_HINT = 'Enter an amount like 1450000 or 1450000.50';

const optionalDate = (message: string) =>
  z.string().refine((value) => value === '' || ISO_DATE.test(value), message);
const optionalAmount = z
  .string()
  .trim()
  .refine((value) => value === '' || AMOUNT.test(value), AMOUNT_HINT);

/** One amount per component code; a blank amount means the component does not apply. */
const lineAmounts = z.record(z.string(), optionalAmount);

/** The server's cap (D51), checked here first so the message sits on the field. */
const note = z.string().max(1000, 'Use 1,000 characters or fewer');

export const exitSchema = z.object({
  last_date: z.string().regex(ISO_DATE, 'Enter the last working day'),
});

export type ExitValues = z.infer<typeof exitSchema>;

const identityFields = {
  full_name: z
    .string()
    .trim()
    .min(1, 'Enter the full name')
    .max(120, 'Use 120 characters or fewer'),
  email: z.string().trim().min(1, 'Enter an email address').max(254, 'Use 254 characters or fewer'),
  // A select starts blank, so the form holds a string and submits one of the genders.
  gender: z.string().pipe(z.enum(GENDERS, { error: 'Choose a gender' })),
  department: z.string().min(1, 'Choose a department'),
  designation: z
    .string()
    .trim()
    .min(1, 'Enter the designation')
    .max(80, 'Use 80 characters or fewer'),
  level: z.string().min(1, 'Choose a level'),
  joining_date: z.string().regex(ISO_DATE, 'Enter the joining date'),
};

export const employeeCreateSchema = z.object({
  ...identityFields,
  country_code: z.string().min(1, 'Choose a country'),
  effective_from: optionalDate('Enter a date, or leave it blank to use the joining date'),
  bonus_annual: optionalAmount,
  note,
  lines: lineAmounts,
});

/** What the form holds, and what a valid submit hands over. */
export type EmployeeCreateFields = z.input<typeof employeeCreateSchema>;
export type EmployeeCreateValues = z.output<typeof employeeCreateSchema>;

export const identitySchema = z.object(identityFields);

export type IdentityFields = z.input<typeof identitySchema>;
export type IdentityValues = z.output<typeof identitySchema>;

export const revisionSchema = z.object({
  effective_from: z.string().regex(ISO_DATE, 'Enter the date the revision takes effect'),
  bonus_annual: optionalAmount,
  note,
  lines: lineAmounts,
});

export type RevisionValues = z.infer<typeof revisionSchema>;
