import { Button } from '@mui/material';
import { Link } from 'react-router';

import { EmptyState } from '../components/layout/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';

export function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState
        message="There is nothing at this address. Go back to the directory."
        action={
          <Button component={Link} to="/employees" variant="outlined">
            Go to the directory
          </Button>
        }
      />
    </>
  );
}
