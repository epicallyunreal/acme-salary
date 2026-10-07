import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';

// Step 3 adds the QueryClientProvider, the theme and a MemoryRouter here, so every component
// test renders inside the same providers as the app.
function Providers({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function renderWithProviders(ui: ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: Providers, ...options });
}
