import { Alert, LinearProgress } from '@mui/material';
import { useCallback } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router';

import { useImportList } from '../api/imports';
import { usePastLastPage } from '../components/grid/usePastLastPage';
import { BatchList, PAGE_SIZE } from '../components/imports/BatchList';
import { TemplateMenu } from '../components/imports/TemplateMenu';
import { UploadDropzone } from '../components/imports/UploadDropzone';
import { EmptyState } from '../components/layout/EmptyState';
import { ErrorState } from '../components/layout/ErrorState';
import { PageHeader } from '../components/layout/PageHeader';

/** Imports (SPEC section 10): the dropzone with the template, and every batch so far. A staged
 * file opens its review page. */
export function Imports() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Math.floor(Number(searchParams.get('page'))) || 1);
  const imports = useImportList(page);
  const goTo = useCallback(
    (next: number) => setSearchParams(next > 1 ? { page: String(next) } : {}, { replace: true }),
    [setSearchParams],
  );
  const pastLast = usePastLastPage({
    error: imports.error,
    count: imports.data?.count,
    fresh: !imports.isPlaceholderData && !imports.isFetching,
    page,
    pageSize: PAGE_SIZE,
    goTo,
  });
  const navigate = useNavigate();
  // Arrived from the Demo data page's reset (D72): the state says what to do next, while nothing
  // is imported yet. Back or a reload after the base import shows it no more.
  const reset = (useLocation().state as { reset?: unknown } | null)?.reset;
  const empty = imports.data?.count === 0;

  return (
    <>
      <PageHeader title="Imports" actions={<TemplateMenu />} />
      {reset && empty ? (
        <Alert severity="success" role="status" sx={{ mb: 4 }}>
          The database is empty. Import base-15000.xlsx to start.
        </Alert>
      ) : null}
      <UploadDropzone onUploaded={(batch) => navigate(`/imports/${batch.id}`)} />
      {imports.isError && !pastLast ? (
        <ErrorState what="the imports" onRetry={() => void imports.refetch()} />
      ) : imports.isPending || !imports.data ? (
        <LinearProgress aria-label="Loading the imports" />
      ) : imports.data.count === 0 ? (
        <EmptyState message="No imports yet. Download the template, fill it in and drop it here." />
      ) : (
        <BatchList
          batches={imports.data.results}
          count={imports.data.count}
          page={page}
          onPageChange={(next) => setSearchParams(next > 1 ? { page: String(next) } : {})}
        />
      )}
    </>
  );
}
