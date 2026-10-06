---
name: frontend-page
description: Recipe for adding a React page or a grid in this codebase with MUI, MUI X DataGrid, TanStack Query and MSW tests. Use when adding a route from docs/SPEC.md section 10, a server-side grid, or when the user says "build the X page".
---

# Add a page

Check `docs/SPEC.md` section 10 for the route and what the page holds. Pages live in `frontend/src/pages/`, shared pieces in `src/components/`, API code in `src/api/`.

1. API layer first. Typed request function and TanStack Query hook in `src/api/<domain>.ts`. Query keys include every filter, so a filter change refetches. Mutations invalidate the queries they affect.
2. MSW handler in `src/test/handlers.ts` with a realistic fixture (a few rows, both currencies, at least one exited employee where relevant).
3. Page component. Authenticated layout, page title, loading and error states, empty state with a sentence that says what to do next.
4. Grids. MUI X DataGrid with `paginationMode`, `sortingMode` and `filterMode` set to `server`. Map the grid's pagination model, sort model and the FilterBar values onto the API params through the shared adapter in `src/components/grid/serverModel.ts`. Page sizes 25, 50, 100. Money columns use the `src/lib/money` formatter and show local currency and the reporting currency side by side where the spec says so.
5. Forms. `react-hook-form` with a `zod` schema that mirrors the API's input serializer. Server field errors map back onto the form fields.
6. Route. Register in the router. Deep links work: filters and page live in the URL search params.
7. Tests with Vitest and Testing Library: renders with fixture data, filter change calls the API with the right params, error state shows, and for forms the validation message appears. Query by role and label.
8. Keyboard and labels. Every input has a label. Focus is visible. Dialogs trap focus. Use MUI components rather than custom controls.
