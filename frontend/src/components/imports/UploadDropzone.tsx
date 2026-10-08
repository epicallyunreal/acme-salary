import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined';
import { Box, Button, LinearProgress, Typography } from '@mui/material';
import { type DragEvent, useRef, useState } from 'react';

import { listImports, useUploadImport } from '../../api/imports';
import type { ImportBatch } from '../../api/types';
import { useBusy } from '../busy/busyContext';
import type { FormMessage } from '../forms/applyServerErrors';
import { ErrorSummary } from '../forms/ErrorSummary';
import { uploadProblems } from './uploadProblems';

/** The server refuses more with a 413 (SPEC section 8); checked here first, so a large file is
 * not sent only to be refused. */
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

interface UploadDropzoneProps {
  onUploaded: (batch: ImportBatch) => void;
}

const GAVE_UP = 'The server may still be working, or the file was refused; check the batch list.';

/** The newest batch there is, read as an upload is sent, so a request the proxy cuts can find
 * the batch it made: one newer than that, with the file's name. Null when the list cannot be
 * read, and a cut upload is then not waited for, since an older batch of the same name could
 * pass for the one made (D72). */
async function newestBatchId(): Promise<number | null> {
  try {
    return (await listImports(1)).results[0]?.id ?? 0;
  } catch {
    return null;
  }
}

/** Drop a sheet, or choose one with the button: dragging is never the only way (WCAG 2.5.7). */
export function UploadDropzone({ onUploaded }: UploadDropzoneProps) {
  const upload = useUploadImport();
  const { busy: running, run } = useBusy();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [locating, setLocating] = useState(false);
  const busy = upload.isPending || locating || running !== null;
  const [problems, setProblems] = useState<FormMessage[]>([]);
  const [attempt, setAttempt] = useState(0);

  const refuse = (found: FormMessage[]) => {
    setProblems(found);
    setAttempt((count) => count + 1);
  };

  const send = async (file: File) => {
    setProblems([]);
    if (file.size > MAX_UPLOAD_BYTES) {
      refuse([{ key: null, message: 'upload is larger than the 10 MB limit' }]);
      return;
    }
    setLocating(true);
    const newestId = await newestBatchId();
    setLocating(false);
    // The staging runs behind the busy dialog (D72). The proxy may cut the request while the
    // server reads on: the batch then appears in the list, newer than the newest before it.
    const result = await run(`Staging ${file.name}\u2026`, () => upload.mutateAsync(file), {
      failedTitle: 'The file was not staged',
      problems: uploadProblems,
      cut: GAVE_UP,
      gaveUp: GAVE_UP,
      recover:
        newestId === null
          ? undefined
          : async () => {
              const page = await listImports(1);
              return (
                page.results.find(
                  (candidate) => candidate.id > newestId && candidate.file_name === file.name,
                ) ?? null
              );
            },
    });
    if (result.ok) onUploaded(result.value);
  };

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file && !busy) void send(file);
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
          disabled={busy}
          startIcon={<UploadFileOutlinedIcon fontSize="small" />}
        >
          Choose a file
        </Button>
        <input
          ref={input}
          type="file"
          accept=".xlsx,.csv"
          hidden
          disabled={busy}
          aria-label="Spreadsheet to import"
          onChange={(event) => {
            const file = event.target.files?.[0];
            // Cleared, so choosing the same file again after fixing it still uploads.
            event.target.value = '';
            if (file) void send(file);
          }}
        />
        {locating ? (
          <Box sx={{ width: '100%', maxWidth: 360 }}>
            <LinearProgress aria-label="Sending the file" />
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
