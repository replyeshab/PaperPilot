import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the Vite dev server forwards /api to the local FastAPI backend,
// so the browser never has to deal with CORS locally.
const backend = process.env.VITE_DEV_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: backend, changeOrigin: true } },
  },
  preview: { port: 4173 },
})
