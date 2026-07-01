/* Service Worker (PWA): precache powłoki + powiadomienia Web Push.
   Wersja „vanilla" (bez workbox). self.__WB_MANIFEST jest wstrzykiwane przez
   vite-plugin-pwa (injectManifest) i tu używane jako lista plików do precache. */

const PRECACHE = (self.__WB_MANIFEST || []).map((e) => (typeof e === 'string' ? e : e.url))
const CACHE = 'grafik-cache-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll([...new Set([...PRECACHE, '/'])]))
      .catch(() => {}),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.pathname.startsWith('/api/')) return

  // Shell HTML (nawigacja): NETWORK-FIRST — po deployu od razu świeża wersja frontu
  // (koniec ze starym, zacache'owanym UI, np. „[object]" we współpracownikach). Offline → cache.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put('/', copy)).catch(() => {})
          return res
        })
        .catch(() => caches.match(req).then((c) => c || caches.match('/'))),
    )
    return
  }

  // Reszta (hashowane JS/CSS/fonty): cache-first — szybko i bez ryzyka nieaktualności
  // (zmiana zawartości = nowa nazwa pliku). API zawsze z sieci (nie cache'ujemy danych).
  event.respondWith(
    caches.match(req).then(
      (cached) =>
        cached ||
        fetch(req)
          .then((res) => {
            const copy = res.clone()
            caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {})
            return res
          })
          .catch(() => caches.match('/')),
    ),
  )
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
