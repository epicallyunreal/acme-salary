// zod schemas that mirror the input serializers (DESIGN section 6). Dates and amounts stay
// strings, so no float arithmetic happens in the browser; the server runs the business rules.

import { z } from 'zod';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const exitSchema = z.object({
  last_date: z.string().regex(ISO_DATE, 'Enter the last working day'),
});

export type ExitValues = z.infer<typeof exitSchema>;
