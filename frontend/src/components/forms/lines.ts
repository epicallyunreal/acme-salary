// The record lines of a form: what goes on the wire, and the preview beside the inputs.

import type { CompensationRecord, LineInput, SalaryComponent } from '../../api/types';

/** The non-blank amounts, in the components' order, as the API's `lines`. The order is kept so
 * a per-item server error can be put back on the line it came from (D46). */
export function linesToSend(
  components: SalaryComponent[],
  amounts: Record<string, string> | undefined,
): LineInput[] {
  return components
    .map((component) => ({
      component: component.code,
      annual_amount: (amounts?.[component.code] ?? '').trim(),
    }))
    .filter((line) => line.annual_amount !== '');
}

/** A record's lines as form values, so a revision starts from the latest amounts. */
export function amountsOf(record: CompensationRecord | null | undefined): Record<string, string> {
  return Object.fromEntries(
    (record?.lines ?? []).map((line) => [line.component, line.annual_amount]),
  );
}

export interface PreviewTotals {
  gross: string;
  net: string;
  totalCost: string;
}

/** Gross, net and total cost as the server will compute them. Number() is used for display
 * only and the result is labelled a preview (DESIGN section 6): the saved totals come from the
 * server's Decimal arithmetic. Amounts that do not parse count as zero here. */
export function previewTotals(
  components: SalaryComponent[],
  amounts: Record<string, string> | undefined,
  bonus: string | undefined,
): PreviewTotals {
  const value = (text: string | undefined) => {
    const parsed = Number((text ?? '').trim());
    return Number.isFinite(parsed) ? parsed : 0;
  };
  let earnings = value(bonus);
  let deductions = 0;
  let employer = 0;
  for (const component of components) {
    const amount = value(amounts?.[component.code]);
    if (component.kind === 'earning') earnings += amount;
    else if (component.kind === 'deduction') deductions += amount;
    else employer += amount;
  }
  return {
    gross: earnings.toFixed(2),
    net: (earnings - deductions).toFixed(2),
    totalCost: (earnings + employer).toFixed(2),
  };
}
