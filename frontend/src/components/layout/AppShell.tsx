import PeopleOutlinedIcon from '@mui/icons-material/PeopleOutlined';
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import {
  Box,
  Button,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
} from '@mui/material';
import { NavLink, Outlet, useMatch, useNavigate } from 'react-router';

import { useLogout, useMe } from '../../api/auth';

const NAV_WIDTH = 208;

// The dashboard joins this list in step 6.
const NAV_ITEMS = [
  { label: 'Employees', to: '/employees', pattern: '/employees/*', Icon: PeopleOutlinedIcon },
  { label: 'Imports', to: '/imports', pattern: '/imports/*', Icon: UploadFileOutlinedIcon },
];

function NavItem({ label, to, pattern, Icon }: (typeof NAV_ITEMS)[number]) {
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

/** Left navigation, a top bar with the signed-in email and Sign out, and the page outlet. */
export function AppShell() {
  const { data: user } = useMe();
  const signOut = useLogout();
  const navigate = useNavigate();

  const onSignOut = () => {
    signOut.mutate(undefined, { onSettled: () => navigate('/login', { replace: true }) });
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Box
        component="nav"
        aria-label="Main"
        sx={{
          width: NAV_WIDTH,
          flexShrink: 0,
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
      </Box>
      <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <Box
          component="header"
          sx={{
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
        <Box component="main" sx={{ p: 6, flex: 1, minWidth: 0 }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
