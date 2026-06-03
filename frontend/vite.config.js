import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend "Grafik Pracy". Budowany do frontend/dist i serwowany przez FastAPI
// pod tym samym originem co API (dzięki czemu względne /api dalej działa).
// W trybie dev Vite serwuje na :5173 i proxuje /api -> uvicorn (127.0.0.1:8000).
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
