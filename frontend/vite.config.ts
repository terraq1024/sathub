import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The enterprise dev server usually occupies :8000; run the OSS edition on
// :8002 and :5174 so both editions can run side by side.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true
      }
    }
  }
});
