import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { Alert, Button, CircularProgress, Menu, MenuItem, Snackbar, Tooltip } from '@mui/material';
import { type MouseEvent, useId, useState } from 'react';

import { EXPORT_FILES, type ExportFile } from '../api/exports';

/** What each format is called in the menu. */
const FORMATS: Record<ExportFile, string> = { csv: 'CSV', xlsx: 'Excel (.xlsx)', json: 'JSON' };

interface ExportMenuProps {
  /** The button's accessible name and tooltip, which also names its menu: "Export summary". The
   * button itself reads "Export". */
  label: string;
  /** What a failure names: "Could not export the summary." */
  what: string;
  /** `small` on the dashboard's cards and rate month line, the default in a page header. */
  size?: 'small' | 'medium';
  onExport: (file: ExportFile) => Promise<void>;
}

/** CSV, Excel or JSON of what the page shows (SPEC F6). A large file takes a few seconds, so the
 * trigger shows a spinner meanwhile and ignores a second click; it keeps its focus throughout. */
export function ExportMenu({ label, what, size = 'medium', onExport }: ExportMenuProps) {
  const menuId = useId();
  const triggerId = useId();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const open = (event: MouseEvent<HTMLElement>) => {
    if (!busy) setAnchor(event.currentTarget);
  };
  const choose = (file: ExportFile) => {
    // A second click can land while the menu fades out.
    if (busy) return;
    setAnchor(null);
    setBusy(true);
    onExport(file)
      .catch(() => setFailed(true))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <Tooltip title={label}>
        <Button
          id={triggerId}
          variant="outlined"
          size={size}
          // Beside a long card title the button keeps its width and the title wraps instead.
          sx={{ flexShrink: 0, whiteSpace: 'nowrap' }}
          startIcon={
            busy ? (
              <CircularProgress size={16} aria-hidden />
            ) : (
              <FileDownloadOutlinedIcon fontSize="small" />
            )
          }
          endIcon={<ArrowDropDownIcon />}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={anchor ? true : undefined}
          aria-controls={anchor ? menuId : undefined}
          aria-busy={busy || undefined}
          onClick={open}
        >
          Export
        </Button>
      </Tooltip>
      <Menu
        id={menuId}
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ list: { 'aria-labelledby': triggerId } }}
      >
        {EXPORT_FILES.map((file) => (
          <MenuItem key={file} onClick={() => choose(file)}>
            {FORMATS[file]}
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
