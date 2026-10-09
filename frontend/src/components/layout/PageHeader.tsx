import { Box, Typography } from '@mui/material';
import { type ReactNode, useEffect } from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

/** The h1 of every page with its actions on the right; also sets the document title. */
export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  useEffect(() => {
    document.title = `${title} · ACME Salary`;
  }, [title]);

  return (
    <Box
      sx={{
        display: 'flex',
        // On a narrow window, or zoomed in, the actions go under the title rather than off the
        // side of the page (D75).
        flexWrap: 'wrap',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: 4,
        mb: 5,
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h1">{title}</Typography>
        {subtitle ? (
          <Typography component="div" variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {subtitle}
          </Typography>
        ) : null}
      </Box>
      {actions ? <Box sx={{ display: 'flex', gap: 2, flexShrink: 0 }}>{actions}</Box> : null}
    </Box>
  );
}
