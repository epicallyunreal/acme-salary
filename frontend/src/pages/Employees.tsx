import AddIcon from '@mui/icons-material/Add';
import { Button, Typography } from '@mui/material';
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router';

import { useEmployeeList } from '../api/employees';
import { FilterBar } from '../components/filters/FilterBar';
import { useUrlFilters } from '../components/filters/useUrlFilters';
import { DIRECTORY_HIDDEN_COLUMNS, directoryColumns } from '../components/grid/columns';
import { ServerGrid } from '../components/grid/ServerGrid';
import {
  fromSortModel,
  isFiltered,
  toListParams,
  toPaginationModel,
  toSortModel,
} from '../components/grid/serverModel';
import { ErrorState } from '../components/layout/ErrorState';
import { PageHeader } from '../components/layout/PageHeader';

/** The directory (SPEC F4, section 10): a server-side grid whose state lives in the URL. */
export function Employees() {
  const { state, set, reset } = useUrlFilters();
  const navigate = useNavigate();
  // Stable references: a fresh model each render makes the grid re-apply it, report a change
  // and reset the page.
  const { page, page_size: pageSize, ordering, currency } = state;
  const paginationModel = useMemo(() => toPaginationModel(page, pageSize), [page, pageSize]);
  const sortModel = useMemo(() => toSortModel(ordering), [ordering]);
  const columns = useMemo(() => directoryColumns(currency), [currency]);
  const params = toListParams({ paginationModel, sortModel, filters: state, search: state.search });
  const employees = useEmployeeList(params);
  const filtered = isFiltered(state);
  const count = employees.data?.count;

  return (
    <>
      <PageHeader
        title="Employees"
        actions={
          <Button
            component={Link}
            to="/employees/new"
            variant="contained"
            startIcon={<AddIcon fontSize="small" />}
          >
            Add employee
          </Button>
        }
        subtitle={
          count === undefined ? undefined : (
            <Typography component="span" variant="body2" className="num">
              {count.toLocaleString('en-US')} {count === 1 ? 'employee' : 'employees'}
              {filtered ? ' match' : ''}
            </Typography>
          )
        }
      />
      <FilterBar filters={state} onChange={set} onReset={reset} filtered={filtered} />
      {employees.isError ? (
        <ErrorState what="employees" onRetry={() => void employees.refetch()} />
      ) : (
        <ServerGrid
          rows={employees.data?.results ?? []}
          columns={columns}
          rowCount={count ?? 0}
          loading={employees.isPending || employees.isFetching}
          paginationModel={paginationModel}
          onPaginationModelChange={(model) =>
            set({ page: model.page + 1, page_size: model.pageSize })
          }
          sortModel={sortModel}
          onSortModelChange={(model) => set({ ordering: fromSortModel(model) })}
          initialColumnVisibility={DIRECTORY_HIDDEN_COLUMNS}
          onRowClick={(row) => navigate(`/employees/${row.id}`)}
          emptyMessage={
            filtered
              ? 'No employees match these filters. Clear a filter or change the search.'
              : 'No employees yet. Import a spreadsheet or add an employee.'
          }
        />
      )}
    </>
  );
}
