import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { Button } from '@mui/material';
import { Link } from 'react-router';

import { EmployeeForm } from '../components/forms/EmployeeForm';
import { PageHeader } from '../components/layout/PageHeader';

/** The new-employee page (SPEC section 10): identity, bonus and the first record's lines. */
export function NewEmployee() {
  return (
    <>
      <Button
        component={Link}
        to="/employees"
        size="small"
        startIcon={<ArrowBackIcon fontSize="small" />}
        sx={{ mb: 3, ml: -2 }}
      >
        Employees
      </Button>
      <PageHeader title="New employee" />
      <EmployeeForm />
    </>
  );
}
