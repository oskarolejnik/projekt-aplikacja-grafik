// Cienki klient HTTP dla API FastAPI. Względny prefiks /api działa zarówno przy
// serwowaniu produkcyjnego buildu przez backend, jak i przez proxy Vite w dev.
const API = '/api'
const TOKEN_KEY = 'grafik_token'

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
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

export { API }
