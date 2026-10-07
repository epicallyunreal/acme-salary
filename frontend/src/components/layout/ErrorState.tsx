import { Alert, Button } from '@mui/material';

interface ErrorStateProps {
  /** What failed to load, in the user's words: "employees", "this employee". */
  what: string;
  onRetry?: () => void;
}

/** DESIGN section 6: "Could not load <thing>. Check your connection and try again." plus Retry. */
export function ErrorState({ what, onRetry }: ErrorStateProps) {
  return (
    <Alert
      severity="error"
      variant="outlined"
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            Retry
          </Button>
        ) : undefined
      }
    >
      Could not load {what}. Check your connection and try again.
    </Alert>
  );
}
