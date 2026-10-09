import { Button, Stack } from '@mui/material';
import { Link } from 'react-router';

import { EmptyState } from '../components/layout/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';
import { reloadPage } from '../lib/navigation';

/** A page that fails to render, or whose code fails to load, inside the frame, in the app's own
 * words and never the router's page with its stack (D76). */
export function RouteError() {
  return (
    <>
      <PageHeader title="Something went wrong" />
      <EmptyState
        message="This page could not be shown."
        action={
          <Stack direction="row" spacing={1} sx={{ justifyContent: 'center' }}>
            <Button variant="outlined" onClick={() => reloadPage()}>
              Reload
            </Button>
            <Button component={Link} to="/" variant="text">
              Go to the dashboard
            </Button>
          </Stack>
        }
      />
    </>
  );
}
