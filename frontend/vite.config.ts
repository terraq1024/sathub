import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy targets the backend. Override the ports via environment
// variables if they collide with other services on your machine.
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.SATHUB_FRONTEND_PORT) || 5173,
    proxy: {
      '/api': {
        target: process.env.SATHUB_BACKEND_URL || 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
});
