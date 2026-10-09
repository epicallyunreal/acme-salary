import { Box } from '@mui/material';
import type { ReactNode } from 'react';

/** A page whose grid takes the space the rest of it leaves (D75): a column of main's height, with
 * the header, filters and alerts at their natural size and the grid filling what is left. When the
 * grid reaches its floor the column outgrows main, and main scrolls. */
export function FillPage({ children }: { children: ReactNode }) {
  return <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>{children}</Box>;
}
