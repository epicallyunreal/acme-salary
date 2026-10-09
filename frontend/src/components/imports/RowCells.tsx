import { Box, Tooltip } from '@mui/material';

import type { ImportRow, RowMessage } from '../../api/types';
import type { StatusTone } from '../../lib/theme';

function toneOf(messages: RowMessage[]): StatusTone {
  return messages.some((message) => message.severity === 'error') ? 'error' : 'warning';
}

/** A cell as the sheet had it. A cell a message is about is tinted by its worst severity and
 * names the problem on hover; the Messages column says the same in text. Any other cell shows its
 * full value on hover, since the column may cut it short (D75). */
export function SheetCell({ row, field }: { row: ImportRow; field: string }) {
  const value = row.raw[field];
  const text = value === null || value === undefined ? '' : String(value);
  const problems = row.messages.filter(
    (message) => message.field === field && message.severity !== 'info',
  );
  if (!problems.length) return <span title={text}>{text}</span>;
  const tone = toneOf(problems);
  return (
    // describeChild: the value stays the cell's name, the message describes it.
    <Tooltip describeChild title={problems.map((message) => message.message).join(' ')}>
      <Box
        component="span"
        data-severity={tone}
        sx={(theme) => ({
          display: 'block',
          mx: -1,
          px: 1,
          borderRadius: 0.5,
          bgcolor: theme.tokens.status[tone].fill,
          color: theme.tokens.status[tone].text,
          fontWeight: 600,
        })}
      >
        {text || 'blank'}
      </Box>
    </Tooltip>
  );
}

/** Every message on the row, worst first, as text. */
export function RowMessagesCell({ row }: { row: ImportRow }) {
  if (!row.messages.length) return null;
  const order = { error: 0, warning: 1, info: 2 } as const;
  const sorted = [...row.messages].sort((a, b) => order[a.severity] - order[b.severity]);
  return (
    <Box component="ul" sx={{ m: 0, p: 0, py: 1, listStyle: 'none', whiteSpace: 'normal' }}>
      {sorted.map((message, index) => (
        <Box
          component="li"
          key={`${message.field}-${index}`}
          sx={(theme) => ({
            color:
              message.severity === 'info'
                ? theme.palette.text.secondary
                : theme.tokens.status[message.severity].text,
          })}
        >
          {message.severity === 'info' ? null : (
            // The colour is not the only cue: the severity is said in words too.
            <Box component="span" sx={{ fontWeight: 600 }}>
              {message.severity === 'error' ? 'Error: ' : 'Warning: '}
            </Box>
          )}
          {message.message}
        </Box>
      ))}
    </Box>
  );
}
