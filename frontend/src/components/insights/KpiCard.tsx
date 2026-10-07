import { Box, Paper, Typography } from '@mui/material';

interface KpiCardProps {
  label: string;
  /** The figure, without its code. */
  figure: string;
  /** Set apart in a lighter weight beside the figure (DESIGN section 7). */
  currency?: string;
  caption?: string;
  /** The exact figure, where the card shows it rounded. */
  exact?: string;
}

/** One key figure: 32 px, weight 500, the currency code at 14 px beside it. */
export function KpiCard({ label, figure, currency, caption, exact }: KpiCardProps) {
  return (
    <Paper variant="outlined" sx={{ p: 4, flex: '1 1 200px', minWidth: 0 }}>
      <Typography component="p" sx={{ fontSize: 14, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography
        component="p"
        className="num"
        title={exact}
        sx={{ fontSize: 32, lineHeight: '40px', fontWeight: 500, mt: 1 }}
      >
        {currency ? (
          <Box
            component="span"
            sx={{ fontSize: 14, fontWeight: 400, color: 'text.secondary', mr: 1.5 }}
          >
            {currency}
          </Box>
        ) : null}
        <span>{figure}</span>
      </Typography>
      {caption ? (
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
          {caption}
        </Typography>
      ) : null}
    </Paper>
  );
}
