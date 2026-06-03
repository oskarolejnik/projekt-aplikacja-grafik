// Cienki klient HTTP dla API FastAPI. Względny prefiks /api działa zarówno przy
// serwowaniu produkcyjnego buildu przez backend, jak i przez proxy Vite w dev.
const API = '/api'

export async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: {} }
  if (body) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(API + path, opts)
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || res.statusText)
  return data
}

export { API }
