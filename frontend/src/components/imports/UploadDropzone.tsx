import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { Box, Button, LinearProgress, Typography } from '@mui/material';
import { type DragEvent, useRef, useState } from 'react';

import { listImports, useUploadImport } from '../../api/imports';
import type { ImportBatch } from '../../api/types';
import { mayStillBeRunning, waitFor } from '../../lib/poll';
import type { FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { uploadProblems } from './uploadProblems';

/** The server refuses more with a 413 (SPEC section 8); checked here first, so a large file is
 * not sent only to be refused. */
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

interface UploadDropzoneProps {
  onUploaded: (batch: ImportBatch) => void;
  /** The newest batch before this upload, so a cut request can find the one it made (D72). */
  newestId?: number;
}

const STILL_WORKING = 'Still working. The server is reading the file.';
const GAVE_UP = 'The server may still be working, or the file was refused; check the batch list.';

/** Drop a sheet, or choose one with the button: dragging is never the only way (WCAG 2.5.7). */
export function UploadDropzone({ onUploaded, newestId = 0 }: UploadDropzoneProps) {
  const upload = useUploadImport();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const busy = upload.isPending || waiting;
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
      onError: async (error) => {
        if (!mayStillBeRunning(error)) {
          refuse(uploadProblems(error));
          return;
        }
        // The proxy cut the request, but the server reads on: the batch appears in the list.
        setWaiting(true);
        const batch = await waitFor(async () => {
          const page = await listImports(1);
          return page.results.find((candidate) => candidate.id > newestId) ?? null;
        });
        setWaiting(false);
        if (batch) onUploaded(batch);
        else refuse([{ key: null, message: GAVE_UP }]);
      },
    });
  };

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !busy) send(file);
  };

  return (
    <Box component="section" aria-labelledby="upload-title" sx={{ mb: 6 }}>
      <ErrorSummary title="The file was not staged" messages={problems} attempt={attempt} />
      <Box
        role="group"
        aria-label="Drop a spreadsheet here"
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
          Drop a .xlsx or .csv here, or choose a file. Up to 15,000 rows and 10 MB.
        </Typography>
        <Button
          variant="outlined"
          onClick={() => input.current?.click()}
          loading={busy}
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
        {busy ? (
          <Box sx={{ width: '100%', maxWidth: 360 }}>
            <LinearProgress aria-label="Staging the file" />
            {waiting ? (
              <Typography variant="body2" role="status" sx={{ color: 'text.secondary', mt: 2 }}>
                {STILL_WORKING}
              </Typography>
            ) : null}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
