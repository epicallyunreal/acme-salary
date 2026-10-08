import DownloadOutlinedIcon from '@mui/icons-material/DownloadOutlined';
import { Alert, Box, Button, LinearProgress, List, ListItem, Typography } from '@mui/material';
import { useState } from 'react';

import { downloadSampleFile, useSampleFiles } from '../../api/demo';
import type { SampleFile } from '../../api/types';
import { ErrorState } from '../layout/ErrorState';

const NOTES = [
  'After a base import every employee has one record dated at joining, so the trend and the bridge show joins and exits but no pay changes until revision files are imported.',
  'A revision file imported into an empty database creates its employees instead, and the base file then shows those rows as errors. Empty the database and start with the base.',
];

/** The sample files of SPEC F9: each with its name, one line on what it exercises and a
 * Download button, the generated ones disabled while the database is empty (D72). */
export function SampleFiles() {
  const files = useSampleFiles();
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const download = async (file: SampleFile) => {
    setBusy(file.name);
    setFailed(null);
    try {
      await downloadSampleFile(file.name, file.file_name);
    } catch {
      setFailed(`Could not download ${file.file_name}. Check your connection and try again.`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Box component="section" aria-labelledby="sample-files-title" sx={{ mb: 6 }}>
      <Typography
        id="sample-files-title"
        component="h2"
        sx={{ fontSize: 20, lineHeight: '28px', fontWeight: 600, mb: 2 }}
      >
        Sample files
      </Typography>
      {files.isError ? (
        <ErrorState what="the sample files" onRetry={() => void files.refetch()} />
      ) : files.isPending ? (
        <LinearProgress aria-label="Loading the sample files" />
      ) : (
        <List aria-label="Sample files" disablePadding>
          {files.data.files.map((file) => (
            <ListItem
              key={file.name}
              divider
              sx={{ px: 0, py: 3, gap: 4, alignItems: 'flex-start' }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontWeight: 600 }}>{file.file_name}</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
                  {file.description}
                </Typography>
                {file.available ? null : (
                  <Typography variant="body2" sx={{ color: 'warning.main', mt: 0.5 }}>
                    Import the base file first.
                  </Typography>
                )}
              </Box>
              <Button
                variant="outlined"
                size="small"
                aria-label={`Download ${file.file_name}`}
                disabled={!file.available || (busy !== null && busy !== file.name)}
                loading={busy === file.name}
                loadingPosition="start"
                startIcon={<DownloadOutlinedIcon fontSize="small" />}
                onClick={() => void download(file)}
                sx={{ flexShrink: 0, mt: 0.5 }}
              >
                Download
              </Button>
            </ListItem>
          ))}
        </List>
      )}
      {failed ? (
        <Alert severity="error" role="status" sx={{ mt: 3 }}>
          {failed}
        </Alert>
      ) : null}
      {NOTES.map((note) => (
        <Typography key={note} variant="body2" sx={{ color: 'text.secondary', mt: 3 }}>
          {note}
        </Typography>
      ))}
    </Box>
  );
}
