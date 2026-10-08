import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { Button, Menu, MenuItem, Tooltip } from '@mui/material';
import { type MouseEvent, useId, useState } from 'react';

import { ApiError } from '../api/client';
import { EXPORT_FILES, type ExportFile } from '../api/exports';
import { useBusy } from './busy/busyContext';

/** What each format is called in the menu. */
const FORMATS: Record<ExportFile, string> = { csv: 'CSV', xlsx: 'Excel (.xlsx)', json: 'JSON' };

interface ExportMenuProps {
  /** The button's accessible name and tooltip, which also names its menu: "Export summary". The
   * button itself reads "Export". */
  label: string;
  /** What a failure names: "Could not export the summary". */
  what: string;
  /** The file's name before its extension, for the busy dialog: "Preparing employees.csv". */
  name: string;
  /** `small` on the dashboard's cards and rate month line, the default in a page header. */
  size?: 'small' | 'medium';
  onExport: (file: ExportFile) => Promise<void>;
}

/** CSV, Excel or JSON of what the page shows (SPEC F6). A large file takes a few seconds, so the
 * download runs behind the busy dialog and the trigger is off meanwhile (D72). */
export function ExportMenu({ label, what, name, size = 'medium', onExport }: ExportMenuProps) {
  const menuId = useId();
  const triggerId = useId();
  const { busy, run } = useBusy();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const open = (event: MouseEvent<HTMLElement>) => {
    setAnchor(event.currentTarget);
  };
  const choose = (file: ExportFile) => {
    setAnchor(null);
    void run(`Preparing ${name}.${file}\u2026`, () => onExport(file), {
      failedTitle: `Could not export ${what}`,
      problems: (error: ApiError) => [
        {
          key: null,
          message: error.detail() ?? `The file could not be made (error ${error.status}).`,
        },
      ],
      cut: 'The download did not finish. Check your connection and try again.',
    });
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
          startIcon={<FileDownloadOutlinedIcon fontSize="small" />}
          endIcon={<ArrowDropDownIcon />}
          aria-label={label}
          aria-haspopup="menu"
          aria-expanded={anchor ? true : undefined}
          aria-controls={anchor ? menuId : undefined}
          disabled={busy !== null}
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
    </>
  );
}
