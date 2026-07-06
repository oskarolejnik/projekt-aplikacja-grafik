// Cienki klient HTTP dla API FastAPI. Względny prefiks /api działa przy serwowaniu
// buildu przez backend i przez proxy Vite w dev. W aplikacji NATYWNEJ (Capacitor) treść
// jest bundlowana lokalnie, więc /api uderzałoby w apkę — dlatego baza jest KONFIGUROWALNA:
// użytkownik podaje adres swojej instancji (ekran „adres instancji"), zapisujemy go i tu doklejamy.
const API = '/api'
const TOKEN_KEY = 'grafik_token'
const API_BASE_KEY = 'lokalo_api_base'

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

export const getToken = () => localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY)
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
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn
}

export async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: {} }
  const token = getToken()
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (body) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(pelnyUrl(path), opts)

  if (res.status === 401) {
    // Token nieważny/wygasł — czyścimy sesję i powiadamiamy aplikację.
    setToken(null)
    if (onUnauthorized) onUnauthorized()
  }
  if (res.status === 204) return null

  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || res.statusText)
  return data
}

// Pobranie pliku z API z nagłówkiem Bearer (nawigacja window.location NIE niesie tokena, więc
// pliki chronione trzeba ściągać przez fetch → blob → link). Rzuca Error z detalem przy błędzie.
export async function pobierzPlik(path, nazwaPliku) {
  const token = getToken()
  const res = await fetch(pelnyUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (res.status === 401) { setToken(null); if (onUnauthorized) onUnauthorized() }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || res.statusText)
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

export { API }
