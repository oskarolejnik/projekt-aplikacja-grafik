/* Service Worker (PWA): mały precache powłoki, runtime-cache użytych assetów
   i powiadomienia Web Push. self.__WB_MANIFEST jest wstrzykiwane przez
   vite-plugin-pwa (injectManifest). */

const PRECACHE = (self.__WB_MANIFEST || []).map((entry) => (typeof entry === 'string' ? entry : entry.url))
const SHELL_CACHE = 'lokalo-shell-v2'
const ASSET_CACHE = 'lokalo-assets-v2'
const CURRENT_CACHES = new Set([SHELL_CACHE, ASSET_CACHE])
const ASSET_DESTINATIONS = new Set(['script', 'style', 'font', 'image', 'manifest', 'audio', 'video'])

function responseMatchesAsset(request, response) {
  if (!response || !response.ok || response.type === 'opaque') return false

  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('text/html')) return false
  if (request.destination === 'script') return /javascript|ecmascript/.test(contentType)
  if (request.destination === 'style') return contentType.includes('text/css')
  if (request.destination === 'font') return /font|application\/octet-stream/.test(contentType)
  if (request.destination === 'image') return contentType.startsWith('image/')
  if (request.destination === 'manifest') return /json|manifest/.test(contentType)
  if (request.destination === 'audio') return contentType.startsWith('audio/')
  if (request.destination === 'video') return contentType.startsWith('video/')
  return false
}

async function cachedAsset(request) {
  const cached = await caches.match(request)
  if (cached) return cached

  try {
    const response = await fetch(request)
    if (responseMatchesAsset(request, response)) {
      const cache = await caches.open(ASSET_CACHE)
      await cache.put(request, response.clone())
    }
    return response
  } catch (_) {
    // Błąd assetu pozostaje błędem sieci. HTML jako fallback skryptu/CSS powodował
    // mylący błąd MIME i potrafił utrwalić uszkodzony chunk w cache.
    return Response.error()
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((c) => c.addAll([...new Set(PRECACHE)]))
      .catch(() => {}),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => !CURRENT_CACHES.has(key)).map((key) => caches.delete(key)))),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.pathname.startsWith('/api/')) return
  if (url.origin !== self.location.origin) return

  // Shell HTML (nawigacja): NETWORK-FIRST — po deployu od razu świeża wersja frontu
  // (koniec ze starym, zacache'owanym UI, np. „[object]" we współpracownikach). Offline → cache.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const contentType = res.headers.get('content-type') || ''
          if (res.ok && contentType.includes('text/html')) {
            const copy = res.clone()
            caches.open(SHELL_CACHE).then((c) => c.put('/', copy)).catch(() => {})
          }
          return res
        })
        .catch(() => caches.open(SHELL_CACHE).then(async (cache) =>
          (await cache.match('/')) || (await cache.match('index.html')) || Response.error(),
        )),
    )
    return
  }

  // Hashowane JS/CSS/fonty trafiają do cache dopiero, gdy użytkownik faktycznie ich użyje.
  // Dzięki temu instalacja SW nie konkuruje z pierwszym renderem o wszystkie lazy chunki.
  if (ASSET_DESTINATIONS.has(req.destination)) event.respondWith(cachedAsset(req))
})

// Powiadomienie push: wyświetl notyfikację.
self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch (_) {
    data = { body: event.data ? event.data.text() : '' }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'Lokalo', {
      body: data.body || '',
      icon: '/icon.svg',
      badge: '/icon.svg',
      data: { url: data.url || '/' },
    }),
  )
})

// Kliknięcie w powiadomienie: skup istniejące okno lub otwórz nowe.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) if ('focus' in c) return c.focus()
      if (self.clients.openWindow) return self.clients.openWindow(url)
    }),
  )
})
