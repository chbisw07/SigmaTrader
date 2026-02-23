import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // When accessing the dev server via a tunnel (e.g., Cloudflare/ngrok),
    // Vite blocks unknown Host headers by default. Allow our tunnel domains.
    // See: https://vite.dev/config/server-options.html#server-allowedhosts
    // Keep both the apex + wildcard forms; Vite's matching behavior has changed
    // across versions and we want tunnel access to remain stable.
    allowedHosts: ['sigmatrader.co.in', 'www.sigmatrader.co.in', '.sigmatrader.co.in'],
    proxy: {
      // Proxy backend health checks in development so the frontend can call `/health`
      // without hitting the Vite dev server itself.
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
    host: '127.0.0.1',
    port: 5173,
  },
})
