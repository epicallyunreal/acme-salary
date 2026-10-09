import SwapVertIcon from '@mui/icons-material/SwapVert';
import ViewColumnOutlinedIcon from '@mui/icons-material/ViewColumnOutlined';
import { type SvgIconProps, Tooltip } from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  ColumnsPanelTrigger,
  DataGrid,
  type DataGridProps,
  type GridColDef,
  type GridColumnVisibilityModel,
  type GridPaginationModel,
  type GridSortModel,
  type GridValidRowModel,
  Toolbar,
  ToolbarButton,
} from '@mui/x-data-grid';

import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from '../../lib/constants';
import { EmptyState } from '../layout/EmptyState';
import { PageNumbers } from './PageNumbers';

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
  /** One sentence for the empty overlay that says what to do next. */
  emptyMessage: string;
  /** `() => 'auto'` lets a row grow to its content, for cells that hold messages. */
  getRowHeight?: DataGridProps<Row>['getRowHeight'];
}

// jsdom has no layout, so the virtualiser would render no rows under Vitest.
const inTests = import.meta.env.MODE === 'test';

// The grid stands at one height whatever the window, ten compact rows (the owner's choice, D75):
// the 52 px toolbar, the 39 px header, ten 36 px rows, the 52 px pager and the two borders, so a
// default page fits exactly. main scrolls when the page is taller than the window, and the grid
// scrolls its own rows past ten.
export const GRID_HEIGHT = 52 + 39 + DEFAULT_PAGE_SIZE * 36 + 52 + 2;

/** The faint up-down icon a sortable column shows at rest, about 3.4:1 on white (D63). */
function UnsortedIcon({ className, fontSize }: Pick<SvgIconProps, 'className' | 'fontSize'>) {
  return (
    <SwapVertIcon
      className={className}
      fontSize={fontSize}
      sx={{ color: 'text.secondary', opacity: 0.7 }}
    />
  );
}

const SLOTS: DataGridProps['slots'] = {
  toolbar: GridToolbar,
  noRowsOverlay: NoRowsOverlay,
  columnUnsortedIcon: UnsortedIcon,
};

/** Every second row is shaded so rows read apart (D75). */
function rowClassName({ indexRelativeToCurrentPage }: { indexRelativeToCurrentPage: number }) {
  return indexRelativeToCurrentPage % 2 === 1 ? 'odd' : '';
}

/** The column chooser lists only the columns it can hide, so an action column stays out of it. */
function togglable(columns: GridColDef[]): string[] {
  return columns.filter((column) => column.hideable !== false).map((column) => column.field);
}

/**
 * A DataGrid with everything server-side (DESIGN section 6): the page, sort and filters live in
 * the URL, the grid only reports what the user did. The grid's own filter panel is off, the
 * FilterBar is the one place to filter. The pager numbers its pages (D64). Its height is fixed at
 * `GRID_HEIGHT` (D75).
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
  emptyMessage,
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
      showToolbar
      slots={SLOTS}
      slotProps={{
        noRowsOverlay: { message: emptyMessage },
        columnsManagement: { getTogglableColumns: togglable },
        basePagination: { material: { ActionsComponent: PageNumbers } },
      }}
      disableVirtualization={inTests}
      getRowHeight={getRowHeight}
      getRowClassName={rowClassName}
      sx={(theme) => ({
        height: GRID_HEIGHT,
        bgcolor: 'background.paper',
        borderColor: 'divider',
        // Rows read apart (D75): separators a step stronger than the divider, every second row on
        // the page background, and a hover a little firmer than MUI's. The review's severity
        // tints sit on their cells, above the shading.
        '--DataGrid-rowBorderColor': theme.tokens.ruleStrong,
        '& .MuiDataGrid-row.odd': { bgcolor: 'background.default' },
        '& .MuiDataGrid-row:hover': { bgcolor: alpha(theme.tokens.ink, 0.07) },
        '& .MuiDataGrid-columnHeaderTitle': { fontWeight: 600 },
        // MUI hides a column's sort icon until hover. Every sortable column keeps it at rest
        // instead, faint until sorted, and the sorted one shows its arrow in full ink (D63).
        '& .MuiDataGrid-columnHeader--sortable .MuiDataGrid-iconButtonContainer': {
          visibility: 'visible',
          width: 'auto',
        },
        '&& .MuiDataGrid-columnHeader.MuiDataGrid-columnHeader--sortable .MuiDataGrid-sortButton': {
          opacity: 1,
        },
        '& .MuiDataGrid-columnHeader--sorted .MuiDataGrid-sortIcon': { color: 'text.primary' },
      })}
    />
  );
}
