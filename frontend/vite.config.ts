import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The built bundle is served by Django at the site root (SPEC section 14). In development Vite
// serves the app and proxies the API to the Django dev server.
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
});
