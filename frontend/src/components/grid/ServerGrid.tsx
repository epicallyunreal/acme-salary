import ViewColumnOutlinedIcon from '@mui/icons-material/ViewColumnOutlined';
import { Tooltip } from '@mui/material';
import {
  ColumnsPanelTrigger,
  DataGrid,
  type DataGridProps,
  type GridColDef,
  type GridColumnVisibilityModel,
  type GridPaginationModel,
  type GridRowParams,
  type GridSortModel,
  type GridValidRowModel,
  Toolbar,
  ToolbarButton,
} from '@mui/x-data-grid';

import { PAGE_SIZES } from '../../lib/constants';
import { EmptyState } from '../layout/EmptyState';

declare module '@mui/x-data-grid' {
  interface NoRowsOverlayPropsOverrides {
    message: string;
  }
}

function NoRowsOverlay({ message }: { message: string }) {
  return <EmptyState message={message} />;
}

function GridToolbar() {
  return (
    <Toolbar>
      <Tooltip title="Choose columns">
        <ColumnsPanelTrigger render={<ToolbarButton aria-label="Choose columns" />}>
          <ViewColumnOutlinedIcon fontSize="small" />
        </ColumnsPanelTrigger>
      </Tooltip>
    </Toolbar>
  );
}

interface ServerGridProps<Row extends GridValidRowModel> {
  rows: Row[];
  columns: GridColDef<Row>[];
  rowCount: number;
  loading: boolean;
  paginationModel: GridPaginationModel;
  onPaginationModelChange: (model: GridPaginationModel) => void;
  sortModel: GridSortModel;
  onSortModelChange: (model: GridSortModel) => void;
  initialColumnVisibility?: GridColumnVisibilityModel;
  onRowClick?: (row: Row) => void;
  /** One sentence for the empty overlay that says what to do next. */
  emptyMessage: string;
  /** Rows of a given height let the grid size itself; a minimum keeps short lists tidy. */
  height?: number | string;
  /** `() => 'auto'` lets a row grow to its content, for cells that hold messages. */
  getRowHeight?: DataGridProps<Row>['getRowHeight'];
}

// jsdom has no layout, so the virtualiser would render no rows under Vitest.
const inTests = import.meta.env.MODE === 'test';

const SLOTS: DataGridProps['slots'] = { toolbar: GridToolbar, noRowsOverlay: NoRowsOverlay };

/**
 * A DataGrid with everything server-side (DESIGN section 6): the page, sort and filters live in
 * the URL, the grid only reports what the user did. The grid's own filter panel is off, the
 * FilterBar is the one place to filter.
 */
export function ServerGrid<Row extends GridValidRowModel>({
  rows,
  columns,
  rowCount,
  loading,
  paginationModel,
  onPaginationModelChange,
  sortModel,
  onSortModelChange,
  initialColumnVisibility,
  onRowClick,
  emptyMessage,
  height = 'calc(100vh - 280px)',
  getRowHeight,
}: ServerGridProps<Row>) {
  return (
    <DataGrid<Row>
      rows={rows}
      columns={columns}
      rowCount={rowCount}
      loading={loading}
      paginationMode="server"
      sortingMode="server"
      filterMode="server"
      disableColumnFilter
      disableRowSelectionOnClick
      density="compact"
      pageSizeOptions={[...PAGE_SIZES]}
      paginationModel={paginationModel}
      onPaginationModelChange={onPaginationModelChange}
      sortModel={sortModel}
      onSortModelChange={onSortModelChange}
      sortingOrder={['asc', 'desc']}
      initialState={{ columns: { columnVisibilityModel: initialColumnVisibility } }}
      onRowClick={onRowClick ? (params: GridRowParams<Row>) => onRowClick(params.row) : undefined}
      showToolbar
      slots={SLOTS}
      slotProps={{ noRowsOverlay: { message: emptyMessage } }}
      disableVirtualization={inTests}
      getRowHeight={getRowHeight}
      sx={{
        height,
        minHeight: 360,
        bgcolor: 'background.paper',
        borderColor: 'divider',
        '& .MuiDataGrid-row': { cursor: onRowClick ? 'pointer' : 'default' },
        '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 600 },
      }}
    />
  );
}
