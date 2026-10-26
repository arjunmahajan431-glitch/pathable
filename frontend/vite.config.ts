import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const allowedHosts = (process.env.VITE_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: Number(process.env.VITE_PORT ?? 5173),
    strictPort: true,
    allowedHosts: allowedHosts.length > 0 ? allowedHosts : undefined,
    proxy: {
      '/api': {
        target: process.env.PATHABLE_API_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: true,
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
