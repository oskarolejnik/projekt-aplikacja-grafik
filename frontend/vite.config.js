import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Frontend "Grafik Pracy". Budowany do frontend/dist i serwowany przez FastAPI
// pod tym samym originem co API (dzięki czemu względne /api dalej działa).
// W trybie dev Vite serwuje na :5173 i proxuje /api -> uvicorn (127.0.0.1:8000).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      registerType: 'autoUpdate',
      injectManifest: {
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024, // czcionki bywają duże
      },
      devOptions: { enabled: true, type: 'module' }, // SW działa też w dev (localhost)
      includeAssets: ['pwa-icon.svg', 'pwa-maskable.svg'],
      manifest: {
        name: 'Grafik Pracy',
        short_name: 'Grafik',
        description: 'Grafik pracy, dyspozycyjność i powiadomienia',
        lang: 'pl',
        theme_color: '#1C1C1E',
        background_color: '#1C1C1E',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/pwa-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/pwa-maskable.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
    }),
  ],
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
