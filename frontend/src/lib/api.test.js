// @vitest-environment jsdom
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { api, setToken, setUnauthorizedHandler } from './api'

// Pomocnik: odpowiedź w stylu fetch Response (tylko pola używane przez api()).
const odp = (status, data, ok) => ({
  status,
  ok: ok ?? (status >= 200 && status < 300),
  json: async () => data,
})
const mockFetch = (resp) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue(resp))

beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
afterEach(() => { vi.unstubAllGlobals(); setUnauthorizedHandler(null) })

describe('api()', () => {
  it('GET bez tokenu — prefiks /api, metoda GET, brak Authorization', async () => {
    mockFetch(odp(200, { ok: 1 }))
    const out = await api('/test')
    expect(out).toEqual({ ok: 1 })
    const [url, opts] = fetch.mock.calls[0]
    expect(url).toBe('/api/test')
    expect(opts.method).toBe('GET')
    expect(opts.headers.Authorization).toBeUndefined()
  })

  it('dołącza nagłówek Bearer, gdy token jest w localStorage', async () => {
    setToken('abc123')
    mockFetch(odp(200, {}))
    await api('/me')
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer abc123')
  })

  it('POST z body — Content-Type application/json + serializacja JSON', async () => {
    mockFetch(odp(201, { id: 5 }))
    await api('/x', 'POST', { a: 1 })
    const opts = fetch.mock.calls[0][1]
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(opts.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('204 No Content → zwraca null', async () => {
    mockFetch(odp(204, null))
    expect(await api('/x', 'DELETE')).toBeNull()
  })

  it('odpowiedź !ok → rzuca Error z detail', async () => {
    mockFetch(odp(400, { detail: 'zły input' }))
    await expect(api('/x')).rejects.toThrow('zły input')
  })

  it('401 → czyści token i woła handler onUnauthorized', async () => {
    setToken('stary-token')
    const onUnauth = vi.fn()
    setUnauthorizedHandler(onUnauth)
    mockFetch(odp(401, { detail: 'wygasł' }))
    await expect(api('/x')).rejects.toBeTruthy()   // 401 ma !ok → też rzuca
    expect(localStorage.getItem('grafik_token')).toBeNull()
    expect(onUnauth).toHaveBeenCalledTimes(1)
  })
})
