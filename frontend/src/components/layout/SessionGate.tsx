import { Box, CircularProgress } from '@mui/material';
import { type ReactNode, useEffect, useState } from 'react';

import { bootstrap } from '../../lib/auth';

/** Runs the one refresh on load before anything that needs the session renders. */
export function SessionGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    bootstrap().finally(() => {
      if (active) setReady(true);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!ready) {
    return (
      <Box
        role="status"
        aria-label="Loading"
        sx={{ display: 'grid', placeItems: 'center', minHeight: '100dvh' }}
      >
        <CircularProgress size={28} />
      </Box>
    );
  }
  return children;
}
