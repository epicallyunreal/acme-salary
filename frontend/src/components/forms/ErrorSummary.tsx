import { Alert, AlertTitle, Box, Link } from '@mui/material';
import { useEffect, useRef } from 'react';

import type { FormMessage } from './applyServerErrors';

export interface FieldProblem {
  /** The id of the input, so the summary links to it. */
  inputId: string;
  message: string;
}

interface ErrorSummaryProps {
  title: string;
  /** Field errors after a failed submit, linked to their inputs. */
  fields?: FieldProblem[];
  /** What the server said that no field could hold, each with the key it came under. */
  messages?: FormMessage[];
  /** Changes on every failed submit, and only then does focus move to the summary, so an error
   * found on blur later never pulls focus off the field being edited. */
  attempt?: number;
}

/** The focusable summary at the top of a form: links to each invalid field, and the server's
 * form-level messages with their keys (DESIGN section 6, ui-ux-pro-max "Focusable Error
 * Summary"). Inline field errors stay where they are. */
export function ErrorSummary({
  title,
  fields = [],
  messages = [],
  attempt = 0,
}: ErrorSummaryProps) {
  const ref = useRef<HTMLDivElement>(null);
  const focusedFor = useRef(0);
  const shown = fields.length + messages.length > 0;

  // Once per failed submit, when its problems are on screen: a form's first invalid submit can
  // count the attempt a render before its errors arrive.
  useEffect(() => {
    if (attempt > 0 && shown && focusedFor.current !== attempt) {
      focusedFor.current = attempt;
      ref.current?.focus();
    }
  }, [attempt, shown]);

  if (!shown) return null;

  const focusField = (inputId: string) => (event: React.MouseEvent) => {
    event.preventDefault();
    document.getElementById(inputId)?.focus();
  };

  return (
    <Alert ref={ref} severity="error" variant="outlined" tabIndex={-1} sx={{ mb: 4 }}>
      <AlertTitle>{title}</AlertTitle>
      <Box component="ul" sx={{ m: 0, pl: 4 }}>
        {fields.map(({ inputId, message }) => (
          <li key={`field-${inputId}`}>
            <Link href={`#${inputId}`} onClick={focusField(inputId)} color="inherit">
              {message}
            </Link>
          </li>
        ))}
        {messages.map(({ key, message }, index) => (
          <li key={`server-${index}`}>
            {key ? (
              <Box component="span" sx={{ color: 'text.secondary', mr: 1 }}>
                {key}
              </Box>
            ) : null}
            {message}
          </li>
        ))}
      </Box>
    </Alert>
  );
}
