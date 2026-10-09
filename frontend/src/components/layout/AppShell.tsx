import DatasetOutlinedIcon from '@mui/icons-material/DatasetOutlined';
import HelpOutlineOutlinedIcon from '@mui/icons-material/HelpOutlineOutlined';
import InsertChartOutlinedIcon from '@mui/icons-material/InsertChartOutlined';
import PeopleOutlinedIcon from '@mui/icons-material/PeopleOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import {
  Box,
  Button,
  Divider,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
} from '@mui/material';
import { useLayoutEffect, useRef } from 'react';
import { NavLink, Outlet, useLocation, useMatch, useNavigate } from 'react-router';

import { useLogout, useMe } from '../../api/auth';
import { FRAME_MIN_WIDTH } from '../../lib/constants';
import { Credit } from './Credit';

const NAV_WIDTH = 208;

interface NavEntry {
  label: string;
  to: string;
  pattern: string;
  Icon: typeof InsertChartOutlinedIcon;
}

const NAV_ITEMS: NavEntry[] = [
  { label: 'Dashboard', to: '/', pattern: '/', Icon: InsertChartOutlinedIcon },
  { label: 'Employees', to: '/employees', pattern: '/employees/*', Icon: PeopleOutlinedIcon },
  { label: 'Imports', to: '/imports', pattern: '/imports/*', Icon: UploadFileOutlinedIcon },
];

// The demo's own page and Help sit apart from the work, under a divider (D75).
const SUPPORT_ITEMS: NavEntry[] = [
  { label: 'Demo data', to: '/demo', pattern: '/demo', Icon: DatasetOutlinedIcon },
  { label: 'Help', to: '/help', pattern: '/help', Icon: HelpOutlineOutlinedIcon },
];

function NavItem({ label, to, pattern, Icon }: NavEntry) {
  const selected = useMatch(pattern) !== null;
  return (
    <ListItemButton
      component={NavLink}
      to={to}
      selected={selected}
      aria-current={selected ? 'page' : undefined}
      sx={{
        borderRadius: 1.5,
        mx: 2,
        my: 0.5,
        '&.Mui-selected': { bgcolor: 'info.light', color: 'primary.main' },
      }}
    >
      <ListItemIcon sx={{ minWidth: 32, color: 'inherit' }}>
        <Icon fontSize="small" />
      </ListItemIcon>
      <ListItemText
        primary={label}
        slotProps={{ primary: { sx: { fontWeight: selected ? 600 : 500 } } }}
      />
    </ListItemButton>
  );
}

/** Left navigation, a top bar with the signed-in email and Sign out, and the page outlet, in a
 * frame of the window's height and at least 1024 px wide: the nav and the top bar never scroll,
 * and `main` is the one scroll container (D75). A narrower window scrolls sideways rather than
 * crushing the nav and the filters. */
export function AppShell() {
  const { data: user } = useMe();
  const signOut = useLogout();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  // A new page starts at its top. main takes focus unless the page focused a control of its own, so Page Down and Space scroll the new page without a click first. A
  // change of filters keeps the path, and with it the place on the page.
  useLayoutEffect(() => {
    const main = mainRef.current;
    if (!main) return;
    main.scrollTop = 0;
    if (!main.contains(document.activeElement)) main.focus({ preventScroll: true });
  }, [pathname]);

  const onSignOut = () => {
    signOut.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) });
  };

  return (
    // As tall as the root, which leaves out a sideways scrollbar where 100dvh would not (D75).
    <Box sx={{ display: 'flex', height: '100%', minWidth: FRAME_MIN_WIDTH, overflow: 'hidden' }}>
      <Box
        component="nav"
        aria-label="Main"
        sx={{
          width: NAV_WIDTH,
          flexShrink: 0,
          // A column that scrolls on its own when the window is short, so the credit at its foot
          // follows the items and never covers one (D80).
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
          borderRight: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
          py: 4,
        }}
      >
        <Typography variant="h3" component="div" sx={{ px: 5, pb: 4 }}>
          ACME Salary
        </Typography>
        <List disablePadding>
          {NAV_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </List>
        <Divider sx={{ my: 2, mx: 4 }} />
        <List disablePadding>
          {SUPPORT_ITEMS.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </List>
        <Box sx={{ mt: 'auto', px: 5, pt: 4 }}>
          <Credit />
        </Box>
      </Box>
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Box
          component="header"
          sx={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 4,
            px: 6,
            py: 2,
            borderBottom: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Typography variant="body2" color="text.secondary">
            {user?.email ?? ''}
          </Typography>
          <Button size="small" variant="text" onClick={onSignOut} loading={signOut.isPending}>
            Sign out
          </Button>
        </Box>
        <Box
          component="main"
          ref={mainRef}
          // Focusable from code only, so the keys that scroll reach it after a route change. It is
          // a place to read from, not a control, so it draws no focus ring.
          tabIndex={-1}
          sx={{
            // The containing block of anything a page positions, such as the text a screen reader
            // alone reads, so nothing escapes the scroll container and scrolls the window.
            position: 'relative',
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            overflowY: 'auto',
            p: 6,
            '&:focus-visible': { outline: 'none' },
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
