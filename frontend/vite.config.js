import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Frontend „Lokalo". Budowany do frontend/dist i serwowany przez FastAPI
// pod tym samym originem co API (dzięki czemu względne /api dalej działa).
// W trybie dev Vite serwuje na :5173 i proxuje /api -> uvicorn (127.0.0.1:8000).
export default defineConfig({
  // Znacznik wersji = czas builda (UTC). Pokazywany w panelu admina, żeby od razu wiedzieć,
  // czy wdrożenie (npm run build) faktycznie weszło — czy widać starą wersję z cache.
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString().slice(0, 16).replace('T', ' ')),
  },
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
      includeAssets: ['icon.svg'],
      manifest: {
        // Domyślna, neutralna marka. Per-klient nazwę/ikonę zmienia się przez branding/own build.
        name: 'Lokalo',
        short_name: 'Lokalo',
        description: 'Zarządzanie lokalem gastronomicznym: grafiki, płace, kasa, rezerwacje',
        lang: 'pl',
        theme_color: '#1C1C1E',
        background_color: '#1C1C1E',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
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
  // Testy jednostkowe frontu (Vitest). Domyślnie środowisko 'node' (czyste funkcje z lib/);
  // testy komponentów (jsdom + @testing-library) dojdą osobno.
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
    setupFiles: ['./src/test-setup.js'],
  },
})
