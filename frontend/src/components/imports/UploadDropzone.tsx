import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { Box, Button, LinearProgress, Typography } from '@mui/material';
import { type DragEvent, useRef, useState } from 'react';

import { useUploadImport } from '../../api/imports';
import type { ImportBatch } from '../../api/types';
import type { FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { uploadProblems } from './uploadProblems';

/** The server refuses more with a 413 (SPEC section 8); checked here first, so a large file is
 * not sent only to be refused. */
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

interface UploadDropzoneProps {
  onUploaded: (batch: ImportBatch) => void;
}

/** Drop a sheet, or choose one with the button: dragging is never the only way (WCAG 2.5.7). */
export function UploadDropzone({ onUploaded }: UploadDropzoneProps) {
  const upload = useUploadImport();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);

  const refuse = (found: FormMessage[]) => {
    setProblems(found);
    setAttempt((count) => count + 1);
  };

  const send = (file: File) => {
    setProblems([]);
    if (file.size > MAX_UPLOAD_BYTES) {
      refuse([{ key: null, message: 'upload is larger than the 10 MB limit' }]);
      return;
    }
    upload.mutate(file, {
      onSuccess: onUploaded,
      onError: (error) => refuse(uploadProblems(error)),
    });
  };

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !upload.isPending) send(file);
  };

  return (
    <Box component="section" aria-labelledby="upload-title" sx={{ mb: 6 }}>
      <ErrorSummary title="The file was not staged" messages={problems} attempt={attempt} />
      <Box
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        sx={{
          border: '1.5px dashed',
          borderColor: dragging ? 'primary.main' : 'divider',
          borderRadius: 2,
          bgcolor: dragging ? 'info.light' : 'background.paper',
          px: 6,
          py: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 3,
          textAlign: 'center',
        }}
      >
        <UploadFileOutlinedIcon color="action" />
        <Typography id="upload-title">
          Drop a .xlsx or .csv here, or choose a file. Up to 10,000 rows.
        </Typography>
        <Button
          variant="outlined"
          onClick={() => input.current?.click()}
          loading={upload.isPending}
          loadingPosition="start"
          startIcon={<UploadFileOutlinedIcon fontSize="small" />}
        >
          Choose a file
        </Button>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.csv"
          hidden
          aria-label="Spreadsheet to import"
          onChange={(event) => {
            const file = event.target.files?.[0];
            // Cleared, so choosing the same file again after fixing it still uploads.
            event.target.value = '';
            if (file) send(file);
          }}
        />
        {upload.isPending ? (
          <Box sx={{ width: '100%', maxWidth: 360 }}>
            <LinearProgress aria-label="Staging the file" />
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
