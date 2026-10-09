// The visual direction of DESIGN section 7 as MUI theme tokens. Light only (D28).

import { createTheme } from '@mui/material/styles';

export const tokens = {
  paper: '#F4F5F1',
  surface: '#FFFFFF',
  ink: '#1C2430',
  inkSecondary: '#4F5965',
  inkMuted: '#646C78',
  rule: '#DCE0D8',
  /** The grids' row separators, a step stronger than `rule` so rows read apart: 1.6:1 on white
   * against `rule`'s 1.3:1 (D75). */
  ruleStrong: '#C9CEC4',
  primary: '#2F4A7A',
  primaryDark: '#223760',
  status: {
    success: { text: '#1B6B3A', fill: '#E3F1E7' },
    warning: { text: '#8A5A00', fill: '#FBF0D9' },
    error: { text: '#A32A1F', fill: '#FBE4E1' },
    info: { text: '#35559A', fill: '#E4EAF7' },
    neutral: { text: '#5B6470', fill: '#ECEEF1' },
  },
  series: ['#2A78D6', '#EB6834'] as const,
  chart: { grid: '#E3E6E0', marker: '#646C78' },
  /** The cost mix's own components, beside the two series and the marker grey. Each clears 3:1
   * on white and stands apart from its neighbours in a bar under normal, deutan, protan and
   * tritan vision (D62). */
  mix: {
    ochre: '#A0790A',
    teal: '#00897B',
    plum: '#7B4FA0',
    navy: '#283593',
    purple: '#8E44AD',
    brown: '#8D6E63',
    other: '#7D8590',
  },
} as const;

export type StatusTone = keyof typeof tokens.status;

declare module '@mui/material/styles' {
  interface Theme {
    tokens: typeof tokens;
  }
  interface ThemeOptions {
    tokens?: typeof tokens;
  }
}

const fontFamily = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif';

export const theme = createTheme({
  cssVariables: true,
  tokens,
  palette: {
    mode: 'light',
    background: { default: tokens.paper, paper: tokens.surface },
    text: { primary: tokens.ink, secondary: tokens.inkSecondary },
    divider: tokens.rule,
    primary: { main: tokens.primary, dark: tokens.primaryDark, contrastText: '#FFFFFF' },
    success: { main: tokens.status.success.text, light: tokens.status.success.fill },
    warning: { main: tokens.status.warning.text, light: tokens.status.warning.fill },
    error: { main: tokens.status.error.text, light: tokens.status.error.fill },
    info: { main: tokens.status.info.text, light: tokens.status.info.fill },
  },
  typography: {
    fontFamily,
    fontSize: 14,
    h1: { fontSize: 24, lineHeight: '32px', fontWeight: 600 },
    h2: { fontSize: 20, lineHeight: '28px', fontWeight: 600 },
    h3: { fontSize: 16, lineHeight: '24px', fontWeight: 600 },
    h4: { fontSize: 32, lineHeight: '40px', fontWeight: 500 },
    body1: { fontSize: 14, lineHeight: '20px' },
    body2: { fontSize: 12, lineHeight: '16px' },
    button: { fontSize: 14, fontWeight: 500, textTransform: 'none' },
    caption: { fontSize: 12, lineHeight: '16px', color: tokens.inkMuted },
  },
  shape: { borderRadius: 6 },
  spacing: 4,
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { fontVariantNumeric: 'lining-nums' },
        '.num, .MuiDataGrid-cell--textRight, .MuiDataGrid-columnHeader--numeric': {
          fontVariantNumeric: 'tabular-nums',
        },
        ':focus-visible': {
          outline: `2px solid ${tokens.primary}`,
          outlineOffset: 2,
        },
        '@media (prefers-reduced-motion: reduce)': {
          '*, *::before, *::after': {
            animationDuration: '0.01ms !important',
            animationIterationCount: '1 !important',
            transitionDuration: '0.01ms !important',
          },
        },
      },
    },
    MuiPaper: { defaultProps: { elevation: 0, variant: 'outlined' } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiTextField: { defaultProps: { size: 'small' } },
    MuiFormControl: { defaultProps: { size: 'small' } },
    MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 500 } } },
  },
});
