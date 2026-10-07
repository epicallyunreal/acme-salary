import { Box, TextField, Typography } from '@mui/material';
import { useFormContext, useWatch } from 'react-hook-form';

import type { ComponentKind, SalaryComponent } from '../../api/types';
import { formatMoney } from '../../lib/money';
import { previewTotals } from './lines';

type LinesValues = {
  lines: Record<string, string>;
  bonus_annual: string;
};

const GROUPS: [ComponentKind, string][] = [
  ['earning', 'Earnings'],
  ['deduction', 'Deductions'],
  ['employer_contribution', 'Employer cost'],
];

interface RecordLinesFieldsProps {
  /** The components of the employee's country, in order. */
  components: SalaryComponent[];
  currency: string;
}

/** One annual amount per component of the chosen country, grouped by kind, with a preview of
 * gross, net and total cost. Lives inside a FormProvider whose values carry `lines` and
 * `bonus_annual`. */
export function RecordLinesFields({ components, currency }: RecordLinesFieldsProps) {
  const {
    register,
    control,
    formState: { errors },
  } = useFormContext<LinesValues>();
  const amounts = useWatch({ control, name: 'lines' });
  const bonus = useWatch({ control, name: 'bonus_annual' });
  const preview = previewTotals(components, amounts, bonus);

  return (
    <Box sx={{ display: 'grid', gap: 4 }}>
      {GROUPS.map(([kind, legend]) => {
        const inGroup = components.filter((component) => component.kind === kind);
        if (!inGroup.length) return null;
        return (
          <Box key={kind} component="fieldset" sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
            <Typography component="legend" variant="caption" sx={{ mb: 2 }}>
              {legend}
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                gap: 4,
              }}
            >
              {inGroup.map((component) => {
                const { ref, ...field } = register(`lines.${component.code}`);
                const error = errors.lines?.[component.code];
                return (
                  <TextField
                    key={component.code}
                    {...field}
                    inputRef={ref}
                    id={`line-${component.code}`}
                    label={`${component.name} (${currency})`}
                    error={Boolean(error)}
                    helperText={error?.message ?? (component.code === 'BASE' ? 'Required' : ' ')}
                    slotProps={{ htmlInput: { inputMode: 'decimal', className: 'num' } }}
                  />
                );
              })}
            </Box>
          </Box>
        );
      })}

      <Box
        aria-live="polite"
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          columnGap: 8,
          rowGap: 1,
          px: 4,
          py: 3,
          borderRadius: 1.5,
          bgcolor: 'background.default',
        }}
      >
        <Typography variant="caption">Preview per year</Typography>
        {[
          ['Gross', preview.gross],
          ['Net', preview.net],
          ['Total cost', preview.totalCost],
        ].map(([label, value]) => (
          <Typography key={label} variant="body1" className="num">
            <Box component="span" sx={{ color: 'text.secondary', mr: 1.5 }}>
              {label}
            </Box>
            {formatMoney(value, currency)}
          </Typography>
        ))}
      </Box>
    </Box>
  );
}
