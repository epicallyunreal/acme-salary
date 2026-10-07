import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';

import type { ComponentKind, EmployeeDetail, SalaryComponent } from '../../api/types';
import { formatDate, formatMonth } from '../../lib/dates';
import { formatAmount, formatMoney, formatRate, isZero, monthly } from '../../lib/money';
import { EmptyState } from '../layout/EmptyState';
import { StatusChip } from '../layout/StatusChip';

const KIND_LABEL: Record<ComponentKind, string> = {
  earning: 'Earning',
  deduction: 'Deduction',
  employer_contribution: 'Employer cost',
};

interface FigureProps {
  label: string;
  value: string;
  currency: string;
  /** The same figure in the reporting currency, when that differs from the local one. */
  converted?: string | null;
  convertedCurrency?: string;
  note?: string;
  hero?: boolean;
}

/** One total, local first and large, the reporting currency beneath it. */
function Figure({ label, value, currency, converted, convertedCurrency, note, hero }: FigureProps) {
  return (
    <Box>
      <Typography variant="caption" component="p">
        {label}
      </Typography>
      <Typography
        component="p"
        className="num"
        sx={{ fontSize: hero ? 32 : 20, lineHeight: hero ? '40px' : '28px', fontWeight: 500 }}
      >
        <Box component="span" sx={{ fontSize: 14, color: 'text.secondary', mr: 1.5 }}>
          {currency}
        </Box>
        <span>{formatAmount(value)}</span>
      </Typography>
      {converted && convertedCurrency ? (
        <Typography variant="body1" color="text.secondary" className="num">
          {formatMoney(converted, convertedCurrency)}
        </Typography>
      ) : null}
      {note ? (
        <Typography variant="body2" color="text.secondary" className="num">
          {note}
        </Typography>
      ) : null}
    </Box>
  );
}

/** "from 2026-11-01" or "exited 2026-06-30" from the API, written out for people. */
function shownLabel(label: string): { status: string; text: string } {
  const [word, day] = label.split(' ');
  return { status: word === 'exited' ? 'exited' : 'scheduled', text: `${word} ${formatDate(day)}` };
}

interface CurrentRecordCardProps {
  employee: EmployeeDetail;
  /** The country's components, for the names and kinds of the lines the API sends as codes. */
  components: SalaryComponent[] | undefined;
}

/** The record in force today, or the latest one with its label (SPEC F3): gross is the figure
 * the page is built around; the lines are in the employee's currency, the totals in both. */
export function CurrentRecordCard({ employee, components }: CurrentRecordCardProps) {
  const record = employee.current_record;
  const title = employee.shown_label ? 'Latest record' : 'Current record';

  if (!record) {
    return (
      <Paper component="section" aria-label="Current record" sx={{ mb: 6 }}>
        <EmptyState message="No pay record yet. Add a revision to set one." />
      </Paper>
    );
  }

  const local = record.currency_code;
  const converted = record.converted;
  const other = converted.currency !== local ? converted.currency : undefined;
  const byCode = new Map(components?.map((component) => [component.code, component]));
  const label = employee.shown_label ? shownLabel(employee.shown_label) : null;

  return (
    <Paper component="section" aria-labelledby="current-record-title" sx={{ p: 6, mb: 6 }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 3,
        }}
      >
        <Typography id="current-record-title" variant="h3" component="h2">
          {title}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {label ? <StatusChip status={label.status} label={label.text} /> : null}
          <Typography variant="body2" color="text.secondary">
            Version {record.version}, effective {formatDate(record.effective_from)}
          </Typography>
        </Box>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '2fr 1fr 1fr' },
          gap: 6,
          mt: 4,
          mb: 5,
        }}
      >
        <Figure
          hero
          label="Gross per year"
          value={record.gross_annual}
          currency={local}
          converted={other ? converted.gross_annual : null}
          convertedCurrency={other}
          note={`${formatMoney(monthly(record.gross_annual), local)} a month`}
        />
        <Figure
          label="Net per year"
          value={record.net_annual}
          currency={local}
          converted={other ? converted.net_annual : null}
          convertedCurrency={other}
        />
        <Figure
          label="Total cost per year"
          value={record.total_cost_annual}
          currency={local}
          converted={other ? converted.total_cost_annual : null}
          convertedCurrency={other}
        />
      </Box>

      <Table size="small" aria-label="Pay lines">
        <TableHead>
          <TableRow>
            <TableCell>Component</TableCell>
            <TableCell>Kind</TableCell>
            <TableCell align="right">Annual ({local})</TableCell>
            <TableCell align="right">Monthly ({local})</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {record.lines.map((line) => {
            const component = byCode.get(line.component);
            return (
              <TableRow key={line.component}>
                <TableCell>{component?.name ?? line.component}</TableCell>
                <TableCell>{component ? KIND_LABEL[component.kind] : ''}</TableCell>
                <TableCell align="right" className="num">
                  {formatAmount(line.annual_amount, { fraction: 2 })}
                </TableCell>
                <TableCell align="right" className="num">
                  {formatAmount(monthly(line.annual_amount), { fraction: 2 })}
                </TableCell>
              </TableRow>
            );
          })}
          {isZero(record.bonus_annual) ? null : (
            <TableRow>
              <TableCell>Bonus</TableCell>
              <TableCell>{KIND_LABEL.earning}</TableCell>
              <TableCell align="right" className="num">
                {formatAmount(record.bonus_annual, { fraction: 2 })}
              </TableCell>
              <TableCell align="right" className="num">
                {formatAmount(monthly(record.bonus_annual), { fraction: 2 })}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {other ? (
        <Typography variant="caption" component="p" sx={{ mt: 3 }} className="num">
          {formatMonth(converted.rate_effective_from)} rate: 1 {local} ={' '}
          {formatRate(converted.rate)} {other}
        </Typography>
      ) : null}
    </Paper>
  );
}
