import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config.ts';

// A zone behind UTC, so a date parsed naively would land on the previous day and a test sees it.
process.env.TZ = 'America/New_York';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      setupFiles: ['src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      css: false,
    },
  }),
);
