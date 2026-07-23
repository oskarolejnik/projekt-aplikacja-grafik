// Cienki klient HTTP dla API FastAPI. Względny prefiks /api działa przy serwowaniu
// buildu przez backend i przez proxy Vite w dev. W aplikacji NATYWNEJ (Capacitor) treść
// jest bundlowana lokalnie, więc /api uderzałoby w apkę — dlatego baza jest KONFIGUROWALNA:
// użytkownik podaje adres swojej instancji (ekran „adres instancji"), zapisujemy go i tu doklejamy.
const API = '/api'
const TOKEN_KEY = 'grafik_token'
const API_BASE_KEY = 'lokalo_api_base'
const WORKSTATION_CSRF_COOKIE = 'lokalo_reservation_workstation_csrf'

// Web: pusta baza → względne '/api' (bez zmian, zero regresji). Native: pełny URL instancji.
let API_BASE = (typeof localStorage !== 'undefined' && localStorage.getItem(API_BASE_KEY)) || ''
export const getApiBase = () => API_BASE
export const setApiBase = (url) => {
  API_BASE = (url || '').replace(/\/+$/, '')   // bez końcowego ukośnika
  if (typeof localStorage !== 'undefined') {
    if (API_BASE) localStorage.setItem(API_BASE_KEY, API_BASE)
    else localStorage.removeItem(API_BASE_KEY)
  }
}
const pelnyUrl = (path) => `${API_BASE}${API}${path}`

// Sprawdza, czy pod podanym adresem stoi instancja Lokalo (ekran „adres instancji" w apce).
export async function sprawdzInstancje(bazowyUrl) {
  const b = (bazowyUrl || '').replace(/\/+$/, '')
  try {
    const r = await fetch(`${b}/api/health`, { method: 'GET' })
    return r.ok
  } catch { return false }
}

export const getPersistentToken = () => localStorage.getItem(TOKEN_KEY)
export const clearSessionToken = () => sessionStorage.removeItem(TOKEN_KEY)
export const getToken = () => getPersistentToken() || sessionStorage.getItem(TOKEN_KEY)
// remember=true → sesja trwała (localStorage, przeżywa zamknięcie przeglądarki);
// remember=false → tylko bieżąca sesja (sessionStorage, znika po zamknięciu karty/przeglądarki).
export const setToken = (t, remember = true) => {
  if (!t) {
    localStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    return
  }
  if (remember) {
    localStorage.setItem(TOKEN_KEY, t)
    sessionStorage.removeItem(TOKEN_KEY)
  } else {
    sessionStorage.setItem(TOKEN_KEY, t)
    localStorage.removeItem(TOKEN_KEY)
  }
}

// AuthContext rejestruje tu reakcję na wygaśnięcie sesji (401).
let onUnauthorized = null
let onWorkstationLocked = null
let credentialGeneration = 0
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn
}
export const setWorkstationLockedHandler = (fn) => {
  onWorkstationLocked = fn
}

export const rotateCredentialGeneration = () => {
  credentialGeneration += 1
  return credentialGeneration
}

const readCookie = (name) => {
  if (typeof document === 'undefined') return null
  const prefix = `${encodeURIComponent(name)}=`
  const entry = document.cookie.split(';').map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null
}

export const getWorkstationCsrf = () => readCookie(WORKSTATION_CSRF_COOKIE)
export const clearWorkstationCsrf = () => {
  if (typeof document === 'undefined') return
  document.cookie = `${WORKSTATION_CSRF_COOKIE}=; Path=/; Max-Age=0; SameSite=Strict`
}

const responseCode = (data) => data?.code
  || (data?.detail && typeof data.detail === 'object' ? data.detail.code : null)

const responseMessage = (data, fallback) => {
  if (typeof data?.detail === 'string') return data.detail
  if (data?.detail && typeof data.detail === 'object') {
    return data.detail.message || data.detail.detail || fallback
  }
  return fallback
}

const handleSessionResponse = (status, code, requestToken, requestMarker, requestGeneration) => {
  // A stale response from the previous operator must not clear or lock the
  // credential that replaced the bearer used for this request.
  // Publiczne żądania (np. błędne /auth/login) nie reprezentują żadnej sesji
  // i nie mogą rozgłaszać wylogowania do innych kart.
  if (requestGeneration !== credentialGeneration || !requestMarker) return
  if (requestToken && getToken() !== requestToken) return
  if (status === 401) {
    setToken(null)
    if (onUnauthorized) onUnauthorized()
  }
  if (status === 423 && code === 'WORKSTATION_LOCKED' && onWorkstationLocked) {
    onWorkstationLocked()
  }
}

export const nowyKluczIdempotencji = (scope = 'request') => {
  const losowy = globalThis.crypto?.randomUUID?.()
    || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `${scope}-${losowy}`.slice(0, 128)
}

export async function api(path, method = 'GET', body = null, options = {}) {
  const requestGeneration = credentialGeneration
  const token = getToken()
  const workstationCsrf = getWorkstationCsrf()
  const requestMarker = options.sessionHandling === false ? null : (token || workstationCsrf)
  const opts = {
    method,
    headers: { ...(options.headers || {}) },
    credentials: options.credentials || 'include',
    ...(options.signal ? { signal: options.signal } : {}),
    ...(options.keepalive ? { keepalive: true } : {}),
    ...(options.credentials ? { credentials: options.credentials } : {}),
  }
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (workstationCsrf && !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    opts.headers['X-Lokalo-Workstation-CSRF'] = workstationCsrf
  }
  if (body) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(pelnyUrl(path), opts)

  if (res.status === 401) {
    // Token nieważny/wygasł — czyścimy sesję i powiadamiamy aplikację.
    handleSessionResponse(res.status, null, token, requestMarker, requestGeneration)
  }
  if (res.status === 204) return null

  const data = await res.json().catch(() => ({}))
  const code = responseCode(data)
  if (res.status === 423) {
    handleSessionResponse(res.status, code, token, requestMarker, requestGeneration)
  }
  if (!res.ok) {
    const error = new Error(responseMessage(data, res.statusText))
    error.status = res.status
    error.code = code
    error.availability = data.availability || null
    error.retryAfter = Number.parseInt(res.headers?.get?.('Retry-After') || '', 10) || 0
    throw error
  }
  return data
}

// Pobranie pliku z API z nagłówkiem Bearer (nawigacja window.location NIE niesie tokena, więc
// pliki chronione trzeba ściągać przez fetch → blob → link). Rzuca Error z detalem przy błędzie.
export async function pobierzPlik(path, nazwaPliku) {
  const token = getToken()
  const workstationCsrf = getWorkstationCsrf()
  const requestGeneration = credentialGeneration
  const requestMarker = token || workstationCsrf
  const res = await fetch(pelnyUrl(path), {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (res.status === 401) {
    handleSessionResponse(res.status, null, token, requestMarker, requestGeneration)
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const code = responseCode(data)
    if (res.status === 423) {
      handleSessionResponse(res.status, code, token, requestMarker, requestGeneration)
    }
    const error = new Error(responseMessage(data, res.statusText))
    error.status = res.status
    error.code = code
    throw error
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nazwaPliku
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// Kontrolowany eksport z filtrami w body. Dane wyszukiwania nie trafiają do URL,
// historii przeglądarki ani logów proxy.
export async function pobierzPlikPost(path, body, nazwaPliku, options = {}) {
  const token = getToken()
  const workstationCsrf = getWorkstationCsrf()
  const requestGeneration = credentialGeneration
  const requestMarker = token || workstationCsrf
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  if (workstationCsrf) headers['X-Lokalo-Workstation-CSRF'] = workstationCsrf
  const res = await fetch(pelnyUrl(path), {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify(body || {}),
    ...(options.signal ? { signal: options.signal } : {}),
  })
  if (res.status === 401) {
    handleSessionResponse(res.status, null, token, requestMarker, requestGeneration)
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const code = responseCode(data)
    if (res.status === 423) {
      handleSessionResponse(res.status, code, token, requestMarker, requestGeneration)
    }
    const error = new Error(responseMessage(data, res.statusText))
    error.status = res.status
    error.code = code
    throw error
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = nazwaPliku
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export { API }
