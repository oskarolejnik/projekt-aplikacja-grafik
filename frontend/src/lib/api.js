// Cienki klient HTTP dla API FastAPI. Względny prefiks /api działa zarówno przy
// serwowaniu produkcyjnego buildu przez backend, jak i przez proxy Vite w dev.
const API = '/api'
const TOKEN_KEY = 'grafik_token'

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
  const res = await fetch(API + path, opts)

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
  const res = await fetch(API + path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
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
