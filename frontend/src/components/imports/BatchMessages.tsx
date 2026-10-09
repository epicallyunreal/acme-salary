import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { Box, IconButton, Typography } from '@mui/material';
import { type ReactNode, useState } from 'react';

import { visuallyHidden } from '../../lib/a11y';

export interface BatchMessage {
  text: string;
  tone: 'warning' | 'info';
  /** Set after the text, such as the blocker's Show them. */
  action?: ReactNode;
}

/** The review's messages in one slot at the end of the summary strip (D75): the approve blocker
 * first, then each batch warning, one at a time, read out as they change. With more than one,
 * Previous and Next step through them and wrap around, never on their own. Nothing is shown when
 * there is nothing to say. */
export function BatchMessages({ messages }: { messages: BatchMessage[] }) {
  const [index, setIndex] = useState(0);
  // When the messages change, a skip clearing the blocker or an unskip bringing it back, the slot
  // starts again from the first, so the blocker is always the one shown first.
  const signature = messages.map((message) => message.text).join('\n');
  const [shownFor, setShownFor] = useState(signature);
  if (shownFor !== signature) {
    setShownFor(signature);
    setIndex(0);
  }
  if (!messages.length) return null;
  const shown = Math.min(index, messages.length - 1);
  const message = messages[shown];
  const many = messages.length > 1;
  const step = (by: number) => setIndex((shown + by + messages.length) % messages.length);

  return (
    <Box
      role="group"
      aria-label="Batch messages"
      data-tone={message.tone}
      sx={(theme) => ({
        // The strip's remaining width at the figures' height, under them only when both cannot fit.
        flex: '1 1 320px',
        minWidth: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        px: 3,
        py: 1,
        borderRadius: 1.5,
        bgcolor: theme.tokens.status[message.tone].fill,
        color: theme.tokens.status[message.tone].text,
      })}
    >
      {/* Read out as it changes: the message and where it sits, not the buttons around it. */}
      <Box aria-live="polite" aria-atomic="true" sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          variant="body2"
          // Two lines at most, the whole message on hover.
          title={message.text}
          sx={{
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            color: 'inherit',
            fontWeight: 500,
          }}
        >
          {message.text}
        </Typography>
        {many ? (
          <Box component="span" sx={visuallyHidden}>
            Message {shown + 1} of {messages.length}
          </Box>
        ) : null}
      </Box>
      {message.action ? <Box sx={{ flexShrink: 0 }}>{message.action}</Box> : null}
      {many ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexShrink: 0 }}>
          <IconButton
            size="small"
            color="inherit"
            aria-label="Previous message"
            onClick={() => step(-1)}
          >
            <ChevronLeftIcon fontSize="small" />
          </IconButton>
          <Typography aria-hidden variant="body2" className="num" sx={{ color: 'inherit' }}>
            {shown + 1}/{messages.length}
          </Typography>
          <IconButton
            size="small"
            color="inherit"
            aria-label="Next message"
            onClick={() => step(1)}
          >
            <ChevronRightIcon fontSize="small" />
          </IconButton>
          {/* Where the shown message sits among them, for the eye alone. Two warnings can read
              alike, so each dot is known by its place. */}
          <Box aria-hidden sx={{ display: 'flex', gap: 1 }}>
            {messages.map((_, position) => (
              <Box
                key={position}
                sx={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  bgcolor: 'currentColor',
                  opacity: position === shown ? 1 : 0.3,
                }}
              />
            ))}
          </Box>
        </Box>
      ) : null}
    </Box>
  );
}
