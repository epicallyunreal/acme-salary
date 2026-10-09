import { Link } from '@mui/material';

/** The builder's credit, the owner's choice of 9 October (D80): a quiet caption link that opens
 * nutanprabhat.dev in a new tab and says so, at the foot of the nav and under the login card. */
export function Credit() {
  return (
    <Link
      href="https://nutanprabhat.dev"
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Built by Nutan Prabhat, opens in a new tab"
      variant="caption"
      color="text.secondary"
      underline="hover"
      sx={{ '&:focus-visible': { textDecoration: 'underline' } }}
    >
      Built by Nutan Prabhat
    </Link>
  );
}
