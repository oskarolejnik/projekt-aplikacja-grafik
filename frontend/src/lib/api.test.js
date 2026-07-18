// @vitest-environment jsdom
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import {
  api,
  nowyKluczIdempotencji,
  pobierzPlik,
  rotateCredentialGeneration,
  setToken,
  setUnauthorizedHandler,
  setWorkstationLockedHandler,
} from './api'

// Pomocnik: odpowiedź w stylu fetch Response (tylko pola używane przez api()).
const odp = (status, data, ok) => ({
  status,
  ok: ok ?? (status >= 200 && status < 300),
  json: async () => data,
})
const mockFetch = (resp) => vi.stubGlobal('fetch', vi.fn().mockResolvedValue(resp))

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  document.cookie = 'lokalo_reservation_workstation_csrf=; Path=/; Max-Age=0'
})
afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
  setWorkstationLockedHandler(null)
})

describe('api()', () => {
  it('GET bez tokenu — prefiks /api, metoda GET, brak Authorization', async () => {
    mockFetch(odp(200, { ok: 1 }))
    const out = await api('/test')
    expect(out).toEqual({ ok: 1 })
    const [url, opts] = fetch.mock.calls[0]
    expect(url).toBe('/api/test')
    expect(opts.method).toBe('GET')
    expect(opts.headers.Authorization).toBeUndefined()
    expect(opts.credentials).toBe('include')
  })

  it('dla mutacji sesji stanowiska dodaje CSRF, ale nie wysyła go przy GET', async () => {
    document.cookie = 'lokalo_reservation_workstation_csrf=csrf-123; Path=/'
    mockFetch(odp(204, null))

    await api('/me/reservation-workstation/touch', 'POST')

    expect(fetch.mock.calls[0][1].headers['X-Lokalo-Workstation-CSRF']).toBe('csrf-123')
    mockFetch(odp(200, { ok: true }))
    await api('/me/reservation-workstation')
    expect(fetch.mock.calls[0][1].headers['X-Lokalo-Workstation-CSRF']).toBeUndefined()
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

  it('przekazuje nagłówki operacji, w tym klucz idempotencji', async () => {
    mockFetch(odp(201, { id: 5 }))
    await api('/x', 'POST', { a: 1 }, {
      headers: { 'Idempotency-Key': 'create-001' },
    })
    expect(fetch.mock.calls[0][1].headers['Idempotency-Key']).toBe('create-001')
  })

  it('przekazuje tryb credentials dla publicznej sesji HttpOnly', async () => {
    mockFetch(odp(200, { ok: true }))

    await api('/online/zarzadzanie/platnosc', 'GET', null, {
      credentials: 'include',
    })

    expect(fetch.mock.calls[0][1].credentials).toBe('include')
  })

  it('204 No Content → zwraca null', async () => {
    mockFetch(odp(204, null))
    expect(await api('/x', 'DELETE')).toBeNull()
  })

  it('odpowiedź !ok → rzuca Error z detail', async () => {
    mockFetch(odp(409, {
      detail: 'stolik zajęty',
      code: 'TABLE_CONFLICT',
      availability: { available: false, rule: 'table' },
    }))
    const error = await api('/x').catch((caught) => caught)
    expect(error.message).toBe('stolik zajęty')
    expect(error.status).toBe(409)
    expect(error.code).toBe('TABLE_CONFLICT')
    expect(error.availability).toEqual({ available: false, rule: 'table' })
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

  it('401 anonimowego żądania nie rozgłasza wylogowania aktywnych kart', async () => {
    const onUnauth = vi.fn()
    setUnauthorizedHandler(onUnauth)
    mockFetch(odp(401, { detail: 'Nieprawidłowy login lub hasło.' }))

    await expect(api('/auth/login', 'POST', { login: 'x', haslo: 'y' })).rejects.toBeTruthy()

    expect(onUnauth).not.toHaveBeenCalled()
    expect(localStorage.getItem('grafik_token')).toBeNull()
  })

  it('oczekiwany brak rejestracji urządzenia nie wylogowuje sesji administratora', async () => {
    setToken('admin-token')
    const onUnauth = vi.fn()
    setUnauthorizedHandler(onUnauth)
    mockFetch(odp(401, {
      detail: { code: 'WORKSTATION_NOT_REGISTERED', message: 'Brak stanowiska.' },
    }))

    await expect(api(
      '/reservation-workstations/operators',
      'GET',
      null,
      { sessionHandling: false },
    )).rejects.toBeTruthy()

    expect(localStorage.getItem('grafik_token')).toBe('admin-token')
    expect(onUnauth).not.toHaveBeenCalled()
  })

  it('423 WORKSTATION_LOCKED zachowuje token i woła osobny handler prywatności', async () => {
    setToken('aktywny-token')
    const onLocked = vi.fn()
    setWorkstationLockedHandler(onLocked)
    mockFetch(odp(423, {
      detail: { code: 'WORKSTATION_LOCKED', message: 'Stanowisko jest zablokowane.' },
    }))

    const error = await api('/rezerwacje-stolik').catch((caught) => caught)

    expect(error.status).toBe(423)
    expect(error.code).toBe('WORKSTATION_LOCKED')
    expect(error.message).toBe('Stanowisko jest zablokowane.')
    expect(localStorage.getItem('grafik_token')).toBe('aktywny-token')
    expect(onLocked).toHaveBeenCalledOnce()
  })

  it('zwykłe 423 nie uruchamia blokady stanowiska', async () => {
    const onLocked = vi.fn()
    setWorkstationLockedHandler(onLocked)
    mockFetch(odp(423, { detail: 'Zasób chwilowo zablokowany.', code: 'RESOURCE_LOCKED' }))

    await expect(api('/x')).rejects.toBeTruthy()

    expect(onLocked).not.toHaveBeenCalled()
  })

  it('odrzuca spóźnione 423 poprzedniej generacji sesji cookie', async () => {
    document.cookie = 'lokalo_reservation_workstation_csrf=csrf-old; Path=/'
    const onLocked = vi.fn()
    setWorkstationLockedHandler(onLocked)
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveFetch = resolve })))

    const pending = api('/rezerwacje-stolik')
    rotateCredentialGeneration()
    resolveFetch(odp(423, {
      detail: { code: 'WORKSTATION_LOCKED', message: 'Stara sesja.' },
    }))

    await expect(pending).rejects.toBeTruthy()
    expect(onLocked).not.toHaveBeenCalled()
  })

  it.each([
    ['api()', () => api('/stary-request')],
    ['pobierzPlik()', () => pobierzPlik('/stary-plik', 'raport.xlsx')],
  ])('%s ignoruje spóźnione 401 poprzedniego tokenu', async (_label, request) => {
    setToken('token-operatora-a')
    const onUnauth = vi.fn()
    setUnauthorizedHandler(onUnauth)
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveFetch = resolve })))

    const pending = request()
    setToken('token-operatora-b')
    resolveFetch(odp(401, { detail: 'Stara sesja wygasła.' }))

    await expect(pending).rejects.toBeTruthy()
    expect(localStorage.getItem('grafik_token')).toBe('token-operatora-b')
    expect(onUnauth).not.toHaveBeenCalled()
  })

  it.each([
    ['api()', () => api('/stary-request')],
    ['pobierzPlik()', () => pobierzPlik('/stary-plik', 'raport.xlsx')],
  ])('%s ignoruje spóźnione 423 poprzedniego tokenu', async (_label, request) => {
    setToken('token-operatora-a')
    const onLocked = vi.fn()
    setWorkstationLockedHandler(onLocked)
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn(() => new Promise((resolve) => { resolveFetch = resolve })))

    const pending = request()
    setToken('token-operatora-b')
    resolveFetch(odp(423, {
      detail: { code: 'WORKSTATION_LOCKED', message: 'Stare stanowisko jest zablokowane.' },
    }))

    await expect(pending).rejects.toBeTruthy()
    expect(localStorage.getItem('grafik_token')).toBe('token-operatora-b')
    expect(onLocked).not.toHaveBeenCalled()
  })
})

describe('nowyKluczIdempotencji()', () => {
  it('tworzy drukowalny, krótki klucz ze scope operacji', () => {
    const key = nowyKluczIdempotencji('online-reservation')
    expect(key).toMatch(/^online-reservation-/)
    expect(key.length).toBeLessThanOrEqual(128)
  })
})
