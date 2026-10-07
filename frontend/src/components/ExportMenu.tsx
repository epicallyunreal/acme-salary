import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import {
  Alert,
  Button,
  CircularProgress,
  IconButton,
  Menu,
  MenuItem,
  Snackbar,
  Tooltip,
} from '@mui/material';
import { type MouseEvent, useId, useState } from 'react';

import { EXPORT_FILES, type ExportFile } from '../api/exports';

interface ExportMenuProps {
  /** The menu's accessible name, and the kebab's tooltip: "Export summary". */
  label: string;
  /** What a failure names: "Could not export the summary." */
  what: string;
  /** A labelled button for a page header, or a kebab for a card (DESIGN section 8). */
  variant?: 'button' | 'icon';
  onExport: (file: ExportFile) => Promise<void>;
}

/** CSV, Excel or JSON of what the page shows (SPEC F6). A large file takes a few seconds, so the
 * trigger shows a spinner meanwhile and ignores a second click; it keeps its focus throughout. */
export function ExportMenu({ label, what, variant = 'icon', onExport }: ExportMenuProps) {
  const menuId = useId();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const open = (event: MouseEvent<HTMLElement>) => {
    if (!busy) setAnchor(event.currentTarget);
  };
  const choose = (file: ExportFile) => {
    setAnchor(null);
    setBusy(true);
    onExport(file)
      .catch(() => setFailed(true))
      .finally(() => setBusy(false));
  };
  const trigger = {
    'aria-label': label,
    'aria-haspopup': 'menu' as const,
    'aria-expanded': anchor ? true : undefined,
    'aria-controls': anchor ? menuId : undefined,
    'aria-busy': busy || undefined,
    onClick: open,
  };
  const spinner = <CircularProgress size={16} aria-hidden />;

  return (
    <>
      {variant === 'button' ? (
        <Button
          variant="outlined"
          startIcon={busy ? spinner : <FileDownloadOutlinedIcon fontSize="small" />}
          endIcon={<ArrowDropDownIcon />}
          {...trigger}
        >
          Export
        </Button>
      ) : (
        <Tooltip title={label}>
          {/* MUI's CardHeader action margins, so the kebab fits the title's line. */}
          <IconButton size="small" sx={{ my: -0.5, mr: -1 }} {...trigger}>
            {busy ? spinner : <MoreVertIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      )}
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        {EXPORT_FILES.map(({ file, label: format }) => (
          <MenuItem key={file} onClick={() => choose(file)}>
            {format}
          </MenuItem>
        ))}
      </Menu>
      <Snackbar open={failed} autoHideDuration={6000} onClose={() => setFailed(false)}>
        <Alert severity="error" role="status" onClose={() => setFailed(false)}>
          Could not export {what}. Check your connection and try again.
        </Alert>
      </Snackbar>
    </>
  );
}
