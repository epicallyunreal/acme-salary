import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { z } from 'zod';

import App from './App.tsx';
import './index.css';

// zod would otherwise test `new Function` once, which script-src 'self' (D38) reports.
z.config({ jitless: true });

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
