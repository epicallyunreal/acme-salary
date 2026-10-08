import { Box, Button, Typography } from '@mui/material';
import { useState } from 'react';
import { useNavigate } from 'react-router';

import { ResetDialog } from '../components/demo/ResetDialog';
import { SampleFiles } from '../components/demo/SampleFiles';
import { PageHeader } from '../components/layout/PageHeader';

/** Demo data (SPEC F9, D72): the sample files, and the danger zone that empties the database so
 * a reviewer can run the 10,000-employee import from nothing. */
export function DemoData() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <>
      <PageHeader
        title="Demo data"
        subtitle="The demo runs on a small shared machine, and a large import can take a few minutes."
      />
      <SampleFiles />
      <Box
        component="section"
        aria-labelledby="danger-title"
        sx={{
          border: '1px solid',
          borderColor: 'error.main',
          borderRadius: 1.5,
          p: 4,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 4,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            id="danger-title"
            component="h2"
            sx={{ fontSize: 20, lineHeight: '28px', fontWeight: 600, color: 'error.main' }}
          >
            Danger zone
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            Empty the database to run the base import from nothing. Lookups, exchange rates and your
            login stay.
          </Typography>
        </Box>
        <Button color="error" variant="outlined" onClick={() => setOpen(true)}>
          Empty the database
        </Button>
      </Box>
      <ResetDialog
        open={open}
        onClose={() => setOpen(false)}
        onDone={(deleted) => navigate('/imports', { state: { reset: deleted } })}
      />
    </>
  );
}
