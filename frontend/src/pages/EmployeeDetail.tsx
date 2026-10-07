import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { Alert, Box, Button, LinearProgress, Snackbar, Tab, Tabs, Typography } from '@mui/material';
import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { ApiError } from '../api/client';
import { useCompensationHistory } from '../api/compensation';
import { useEmployee } from '../api/employees';
import { useComponents } from '../api/meta';
import type { CompensationRecord, EmployeeDetail as Employee } from '../api/types';
import { AuditList } from '../components/employee/AuditList';
import { CurrentRecordCard } from '../components/employee/CurrentRecordCard';
import { CancelRevisionDialog, HistoryList } from '../components/employee/HistoryList';
import { ExitDialog } from '../components/forms/ExitDialog';
import { EmptyState } from '../components/layout/EmptyState';
import { ErrorState } from '../components/layout/ErrorState';
import { PageHeader } from '../components/layout/PageHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { formatDate } from '../lib/dates';

type PanelName = 'history' | 'audit';

function EmployeeNotFound() {
  return (
    <>
      <PageHeader title="Employee not found" />
      <EmptyState
        message="This employee does not exist. Go back to the directory."
        action={
          <Button component={Link} to="/employees" variant="outlined">
            Go to the directory
          </Button>
        }
      />
    </>
  );
}

/** Who this is, as labelled facts rather than a run-on line. */
function IdentityFacts({ employee }: { employee: Employee }) {
  const facts: [string, string][] = [
    ['Department', employee.department.name],
    ['Designation', employee.designation],
    ['Level', String(employee.level)],
    ['Country', `${employee.country.name} (${employee.country.currency_code})`],
    ['Email', employee.email],
    ['Joined', formatDate(employee.joining_date)],
  ];
  if (employee.last_date) facts.push(['Last day', formatDate(employee.last_date)]);

  return (
    <Box
      component="dl"
      sx={{ display: 'flex', flexWrap: 'wrap', columnGap: 10, rowGap: 3, m: 0, mb: 6 }}
    >
      {facts.map(([label, value]) => (
        <Box key={label}>
          <Typography component="dt" variant="caption">
            {label}
          </Typography>
          <Typography component="dd" sx={{ m: 0 }}>
            {value}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function Panel({
  name,
  shown,
  children,
}: {
  name: PanelName;
  shown: PanelName;
  children: React.ReactNode;
}) {
  return (
    <Box
      role="tabpanel"
      id={`panel-${name}`}
      aria-labelledby={`tab-${name}`}
      hidden={shown !== name}
    >
      {shown === name ? children : null}
    </Box>
  );
}

function EmployeePage({ employeeId }: { employeeId: number }) {
  const employee = useEmployee(employeeId);
  const history = useCompensationHistory(employeeId);
  const components = useComponents(employee.data?.country.code);
  const [panel, setPanel] = useState<PanelName>('history');
  const [exiting, setExiting] = useState(false);
  const [cancelling, setCancelling] = useState<CompensationRecord | null>(null);
  const [notice, setNotice] = useState({ open: false, text: '' });
  const announce = (text: string) => setNotice({ open: true, text });

  if (employee.isError) {
    if (employee.error instanceof ApiError && employee.error.status === 404) {
      return <EmployeeNotFound />;
    }
    return <ErrorState what="this employee" onRetry={() => void employee.refetch()} />;
  }
  if (employee.isPending) return <LinearProgress aria-label="Loading the employee" />;

  const person = employee.data;

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
      <PageHeader
        title={person.full_name}
        subtitle={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <span className="num">{person.employee_code}</span>
            <StatusChip status={person.status} />
          </Box>
        }
        actions={
          person.last_date ? null : (
            <Button variant="outlined" onClick={() => setExiting(true)}>
              Mark exited
            </Button>
          )
        }
      />
      <IdentityFacts employee={person} />
      <CurrentRecordCard employee={person} components={components.data} />

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 4 }}>
        <Tabs
          value={panel}
          onChange={(_, value: PanelName) => setPanel(value)}
          aria-label="Pay history and audit"
        >
          <Tab value="history" label="History" id="tab-history" aria-controls="panel-history" />
          <Tab value="audit" label="Audit" id="tab-audit" aria-controls="panel-audit" />
        </Tabs>
      </Box>
      <Panel name="history" shown={panel}>
        {history.isError ? (
          <ErrorState what="the pay history" onRetry={() => void history.refetch()} />
        ) : history.isPending ? (
          <LinearProgress aria-label="Loading the pay history" />
        ) : (
          <HistoryList records={history.data} onCancel={setCancelling} />
        )}
      </Panel>
      <Panel name="audit" shown={panel}>
        <AuditList employeeId={employeeId} />
      </Panel>

      <ExitDialog
        employee={person}
        open={exiting}
        onClose={() => setExiting(false)}
        onDone={announce}
      />
      {cancelling ? (
        <CancelRevisionDialog
          employeeId={employeeId}
          record={cancelling}
          onClose={() => setCancelling(null)}
          onDone={announce}
        />
      ) : null}
      <Snackbar
        open={notice.open}
        autoHideDuration={6000}
        onClose={() => setNotice((current) => ({ ...current, open: false }))}
      >
        <Alert
          severity="success"
          role="status"
          onClose={() => setNotice((current) => ({ ...current, open: false }))}
        >
          {notice.text}
        </Alert>
      </Snackbar>
    </>
  );
}

/** The employee page (SPEC section 10): who they are, the record in force, the history and the
 * audit list, with the actions that change them. */
export function EmployeeDetail() {
  const { id } = useParams();
  const employeeId = Number(id);
  if (!Number.isInteger(employeeId) || employeeId <= 0) return <EmployeeNotFound />;
  return <EmployeePage key={employeeId} employeeId={employeeId} />;
}
