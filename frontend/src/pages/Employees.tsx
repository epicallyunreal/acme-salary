import { Typography } from '@mui/material';
import { useNavigate } from 'react-router';

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
  const paginationModel = toPaginationModel(state);
  const sortModel = toSortModel(state);
  const params = toListParams({ paginationModel, sortModel, filters: state, search: state.search });
  const employees = useEmployeeList(params);
  const filtered = isFiltered(state);
  const count = employees.data?.count;

  return (
    <>
      <PageHeader
        title="Employees"
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
          columns={directoryColumns(state.currency)}
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
