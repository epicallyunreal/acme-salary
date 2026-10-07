import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import { Alert, Button, Menu, MenuItem, Snackbar } from '@mui/material';
import { useState } from 'react';

import { downloadTemplate } from '../../api/imports';
import { useCountries } from '../../api/meta';

/** "Download template", for one country's components or for all of them (SPEC section 8). */
export function TemplateMenu() {
  const countries = useCountries();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [failed, setFailed] = useState(false);

  const download = (country?: string) => {
    setAnchor(null);
    downloadTemplate(country).catch(() => setFailed(true));
  };

  return (
    <>
      <Button
        variant="outlined"
        startIcon={<FileDownloadOutlinedIcon fontSize="small" />}
        endIcon={<ArrowDropDownIcon />}
        aria-haspopup="menu"
        aria-expanded={anchor ? 'true' : undefined}
        aria-controls={anchor ? 'template-menu' : undefined}
        onClick={(event) => setAnchor(event.currentTarget)}
      >
        Download template
      </Button>
      <Menu
        id="template-menu"
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={() => setAnchor(null)}
      >
        <MenuItem onClick={() => download()}>All countries</MenuItem>
        {countries.data?.map((country) => (
          <MenuItem key={country.code} onClick={() => download(country.code)}>
            {country.name} ({country.currency_code})
          </MenuItem>
        ))}
      </Menu>
      <Snackbar open={failed} autoHideDuration={6000} onClose={() => setFailed(false)}>
        <Alert severity="error" role="status" onClose={() => setFailed(false)}>
          Could not download the template. Check your connection and try again.
        </Alert>
      </Snackbar>
    </>
  );
}
