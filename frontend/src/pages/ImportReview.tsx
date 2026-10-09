import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Link as MuiLink,
  Snackbar,
  TextField,
  Tooltip,
} from '@mui/material';
import { useMemo, useState } from 'react';
import type { GridSortModel } from '@mui/x-data-grid';
import { Link, useParams, useSearchParams } from 'react-router';

import { ApiError } from '../api/client';
import { useImportBatch, useImportRows, useSkipRow } from '../api/imports';
import type { ImportBatch, ImportRow, ImportRowParams } from '../api/types';
import { CommitField, SEARCH_DELAY_MS } from '../components/filters/FilterBar';
import { importRowColumns } from '../components/grid/columns';
import { ServerGrid } from '../components/grid/ServerGrid';
import { useBusy } from '../components/busy/busyContext';
import { ApproveDialog, DiscardDialog } from '../components/imports/BatchDialogs';
import type { BatchMessage } from '../components/imports/BatchMessages';
import { BatchSummaryStrip } from '../components/imports/BatchSummaryStrip';
import { rowsWord } from '../components/imports/counts';
import { TemplateMenu } from '../components/imports/TemplateMenu';
import { EmptyState } from '../components/layout/EmptyState';
import { ErrorState } from '../components/layout/ErrorState';
import { PageHeader } from '../components/layout/PageHeader';
import { StatusChip } from '../components/layout/StatusChip';
import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from '../lib/constants';
import { visuallyHidden } from '../lib/a11y';
import { formatDate, formatDateTime } from '../lib/dates';

// The review keeps the sheet's order. One empty sort model serves every render, since a new one
// reads to the grid as a sort change, which takes it back to its first page.
const NO_SORT: GridSortModel = [];

const STATUSES = [
  ['', 'All'],
  ['valid', 'Valid'],
  ['warning', 'Warning'],
  ['error', 'Error'],
  ['skipped', 'Skipped'],
] as const;
type StatusFilter = (typeof STATUSES)[number][0];

/** The grid's state lives in the URL, so a filtered page is a link that can be shared. */
function useReviewParams() {
  const [params, setParams] = useSearchParams();
  const pageSize = Number(params.get('page_size'));
  const status = params.get('status') ?? '';
  const state = {
    page: Math.max(1, Math.floor(Number(params.get('page'))) || 1),
    pageSize: (PAGE_SIZES as readonly number[]).includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
    status: (STATUSES.some(([value]) => value === status) ? status : '') as StatusFilter,
    search: params.get('search') ?? '',
  };
  const set = (changes: Partial<typeof state>) => {
    const next = { ...state, ...changes };
    // A new status or search starts again from the first page.
    if (changes.status !== undefined || changes.search !== undefined) next.page = 1;
    const query: Record<string, string> = {};
    if (next.page > 1) query.page = String(next.page);
    if (next.pageSize !== DEFAULT_PAGE_SIZE) query.page_size = String(next.pageSize);
    if (next.status) query.status = next.status;
    if (next.search) query.search = next.search;
    setParams(query);
  };
  return { ...state, set };
}

/** Why Approve is off, in the words of DESIGN section 6, or null when it is on. */
function approveBlocker(batch: ImportBatch): string | null {
  if (batch.status !== 'review') return `This batch is ${batch.status}.`;
  if (batch.error_rows) {
    const them = batch.error_rows === 1 ? 'it' : 'them';
    return `${rowsWord(batch.error_rows)} ${batch.error_rows === 1 ? 'has' : 'have'} errors. Skip ${them} or fix the spreadsheet and upload again.`;
  }
  return null;
}

function BatchState({ batch }: { batch: ImportBatch }) {
  if (batch.status === 'approved') {
    return (
      <Alert severity="success" sx={{ mb: 4 }}>
        Applied {rowsWord(batch.applied_rows)} on {formatDate(batch.approved_at)}:{' '}
        {batch.created_rows} created, {batch.updated_rows} updated, {batch.revised_rows} revised.
      </Alert>
    );
  }
  if (batch.status === 'failed') {
    return (
      <Alert severity="error" sx={{ mb: 4 }}>
        The approve failed and nothing was applied: {batch.error_summary}. Upload the sheet again to
        retry.
      </Alert>
    );
  }
  if (batch.status === 'discarded') {
    return (
      <Alert severity="info" sx={{ mb: 4 }}>
        This batch was discarded. Nothing in it was applied.
      </Alert>
    );
  }
  return null;
}

function ImportNotFound() {
  return (
    <>
      <PageHeader title="Import not found" />
      <EmptyState
        message="This import does not exist. Go back to the imports."
        action={
          <Button component={Link} to="/imports" variant="outlined">
            Go to the imports
          </Button>
        }
      />
    </>
  );
}

function ReviewPage({ batchId }: { batchId: number }) {
  const batch = useImportBatch(batchId);
  const view = useReviewParams();
  const params: ImportRowParams = {
    page: view.page,
    page_size: view.pageSize,
    status: view.status || undefined,
    search: view.search || undefined,
  };
  const rows = useImportRows(batchId, params);
  const { mutate: toggleSkip } = useSkipRow(batchId);
  const [dialog, setDialog] = useState<'approve' | 'discard' | null>(null);
  const { busy } = useBusy();
  const [notice, setNotice] = useState<{ text: string; severity: 'success' | 'error' } | null>(
    null,
  );
  const announce = (text: string) => setNotice({ text, severity: 'success' });
  const paginationModel = useMemo(
    () => ({ page: view.page - 1, pageSize: view.pageSize }),
    [view.page, view.pageSize],
  );
  // Every row of a batch has the sheet's columns, so the first one names them.
  const firstRow = rows.data?.results[0];
  const sheetKey = firstRow ? Object.keys(firstRow.raw).join(',') : '';
  const inReview = batch.data?.status === 'review';
  const columns = useMemo(
    () =>
      importRowColumns(sheetKey ? sheetKey.split(',') : [], {
        canSkip: inReview,
        onToggleSkip: (row: ImportRow) =>
          toggleSkip(
            { rowId: row.id, skip: row.status !== 'skipped' },
            {
              onError: (error) =>
                setNotice({
                  severity: 'error',
                  text:
                    error instanceof ApiError && error.detail()
                      ? `The row did not change: ${error.detail()}.`
                      : 'The row did not change. Check your connection and try again.',
                }),
            },
          ),
      }),
    [sheetKey, inReview, toggleSkip],
  );

  if (batch.isError) {
    if (batch.error instanceof ApiError && batch.error.status === 404) return <ImportNotFound />;
    return <ErrorState what="this import" onRetry={() => void batch.refetch()} />;
  }
  if (batch.isPending) return <LinearProgress aria-label="Loading the import" />;

  const current = batch.data;
  const blocker = approveBlocker(current);
  const filtered = Boolean(view.status || view.search);
  // The strip's one slot (D75): the blocker first, with the way to its rows, then each warning.
  const messages: BatchMessage[] = [
    ...(inReview && blocker
      ? [
          {
            text: blocker,
            tone: 'warning' as const,
            action: (
              <MuiLink
                component="button"
                type="button"
                variant="body2"
                color="inherit"
                underline="always"
                sx={{ fontWeight: 600 }}
                onClick={() => view.set({ status: 'error' })}
              >
                Show them
              </MuiLink>
            ),
          },
        ]
      : []),
    ...current.warnings.map((text) => ({ text, tone: 'info' as const })),
  ];

  return (
    <>
      <Button
        component={Link}
        to="/imports"
        size="small"
        startIcon={<ArrowBackIcon fontSize="small" />}
        sx={{ mb: 3, ml: -2 }}
      >
        Imports
      </Button>
      <PageHeader
        title={current.file_name}
        subtitle={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <StatusChip status={current.status} />
            <span>
              Uploaded {formatDateTime(current.uploaded_at)}
              {current.uploaded_by ? ` by ${current.uploaded_by}` : ''}
            </span>
          </Box>
        }
        actions={
          <>
            <TemplateMenu />
            <Button
              variant="outlined"
              disabled={!inReview || busy !== null}
              onClick={() => setDialog('discard')}
            >
              Discard
            </Button>
            <Tooltip title={blocker ?? ''}>
              {/* A disabled button takes no pointer events, so the span carries the tooltip. */}
              <span>
                <Button
                  variant="contained"
                  disabled={Boolean(blocker) || busy !== null}
                  aria-describedby={inReview && blocker ? 'approve-blocker' : undefined}
                  onClick={() => setDialog('approve')}
                >
                  Approve
                </Button>
              </span>
            </Tooltip>
          </>
        }
      />
      {/* What describes Approve while it is off, whichever message the strip shows (D75). */}
      {inReview && blocker ? (
        <Box component="span" id="approve-blocker" sx={visuallyHidden}>
          {blocker}
        </Box>
      ) : null}
      <BatchSummaryStrip batch={current} messages={messages} />
      <BatchState batch={current} />
      <Box
        component="section"
        aria-label="Filters"
        sx={{ display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center', mb: 4 }}
      >
        <TextField
          label="Status"
          select
          value={view.status}
          onChange={(event) => view.set({ status: event.target.value as StatusFilter })}
          slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
          sx={{ width: 160 }}
        >
          {STATUSES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </TextField>
        <CommitField
          label="Search"
          placeholder="Code or name"
          value={view.search}
          onCommit={(search) => view.set({ search })}
          delay={SEARCH_DELAY_MS}
          width={240}
        />
      </Box>
      {rows.isError ? (
        <ErrorState what="the rows" onRetry={() => void rows.refetch()} />
      ) : (
        <ServerGrid
          rows={rows.data?.results ?? []}
          columns={columns}
          rowCount={rows.data?.count ?? 0}
          loading={rows.isPending || rows.isFetching}
          paginationModel={paginationModel}
          onPaginationModelChange={(model) =>
            view.set({ page: model.page + 1, pageSize: model.pageSize })
          }
          sortModel={NO_SORT}
          onSortModelChange={() => undefined}
          getRowHeight={() => 'auto'}
          emptyMessage={
            filtered
              ? 'No rows with this status. Choose another status.'
              : 'This file has no data rows.'
          }
        />
      )}
      {dialog === 'approve' ? (
        <ApproveDialog batch={current} onClose={() => setDialog(null)} onDone={announce} />
      ) : null}
      {dialog === 'discard' ? (
        <DiscardDialog batch={current} onClose={() => setDialog(null)} onDone={announce} />
      ) : null}
      <Snackbar open={Boolean(notice)} autoHideDuration={6000} onClose={() => setNotice(null)}>
        <Alert
          severity={notice?.severity ?? 'success'}
          role="status"
          onClose={() => setNotice(null)}
        >
          {notice?.text}
        </Alert>
      </Snackbar>
    </>
  );
}

/** Import review (SPEC section 10, F2): the summary, the rows with their messages, skip and
 * unskip, and the batch's approve and discard. */
export function ImportReview() {
  const { id } = useParams();
  const batchId = Number(id);
  if (!Number.isInteger(batchId) || batchId <= 0) return <ImportNotFound />;
  return <ReviewPage key={batchId} batchId={batchId} />;
}
