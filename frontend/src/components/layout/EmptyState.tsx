import { Box, Typography } from '@mui/material';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  /** One sentence that says what to do next. */
  message: string;
  action?: ReactNode;
}

export function EmptyState({ message, action }: EmptyStateProps) {
  return (
    <Box sx={{ py: 10, px: 4, textAlign: 'center' }}>
      <Typography color="text.secondary">{message}</Typography>
      {action ? <Box sx={{ mt: 3 }}>{action}</Box> : null}
    </Box>
  );
}
