// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, confirmMock, toastMock, idempotencyMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  toastMock: vi.fn(),
  idempotencyMock: vi.fn(),
}))

vi.mock('../lib/api', () => ({
  api: apiMock,
  nowyKluczIdempotencji: idempotencyMock,
}))
vi.mock('../context/BrandingContext', () => ({ useBranding: () => ({ nazwa_lokalu: 'Bistro Testowe' }) }))
vi.mock('../components/ui/Toast', () => ({ useToast: () => ({ toast: toastMock, confirm: confirmMock }) }))
vi.mock('../components/Logo', () => ({ Logo: () => <span aria-hidden="true">Logo</span> }))

import RezerwacjaWidget from './RezerwacjaWidget'

const CONFIG_V2 = {
  version: 2,
  hold_ttl_seconds: 600,
  privacy: { notice_version: 'privacy-2026-07', notice_label: 'Zapoznałem/am się z informacją o przetwarzaniu danych.' },
  marketing: { version: 'marketing-2026-07' },
  sensitive: { version: 'sensitive-2026-07' },
}

const reservation = (status = 'potwierdzona') => ({
  data: '2035-07-16',
  godz_od: '18:00',
  godz_do: '20:00',
  liczba_osob: 2,
  nazwisko: 'Jan Kowalski',
  status,
})

const deferred = () => {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const renderReadyWidget = async () => {
  render(<RezerwacjaWidget />)
  expect(await screen.findByRole('heading', { name: 'Znajdź stolik' })).toBeInTheDocument()
}

const searchFor = async ({ date = '2035-07-16', people = '2' } = {}) => {
  fireEvent.change(screen.getByLabelText('Data'), { target: { value: date } })
  fireEvent.change(screen.getByLabelText('Liczba osób'), { target: { value: people } })
  fireEvent.click(screen.getByRole('button', { name: 'Pokaż wolne godziny' }))
}

const fillRequiredGuestData = () => {
  fireEvent.change(screen.getByLabelText('Imię i nazwisko'), { target: { value: 'Jan Kowalski' } })
  fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'jan@example.com' } })
  fireEvent.click(screen.getByLabelText(CONFIG_V2.privacy.notice_label))
}

beforeEach(() => {
  sessionStorage.clear()
  window.history.replaceState({}, '', '/')
  let key = 0
  idempotencyMock.mockReset()
  idempotencyMock.mockImplementation((scope) => `${scope}-${++key}`)
  confirmMock.mockReset()
  confirmMock.mockResolvedValue(true)
  toastMock.mockReset()
  apiMock.mockReset()
  apiMock.mockImplementation((path, method = 'GET') => {
    if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
    if (path.startsWith('/online/dostepnosc')) {
      return Promise.resolve({ sloty: [{ godz_od: '18:00', dostepny: true }] })
    }
    if (path === '/online/hold' && method === 'POST') {
      return Promise.resolve({
        hold_token: 'hold-secret',
        expires_at: new Date(Date.now() + 600_000).toISOString(),
        rezerwacja: reservation(),
      })
    }
    if (path === '/online/hold' && method === 'DELETE') return Promise.resolve(null)
    if (path === '/online/rezerwacja' && method === 'POST') {
      return Promise.resolve({ management_token: 'management-1', rezerwacja: reservation() })
    }
    if (path === '/online/zarzadzanie/odwolaj' && method === 'POST') {
      return Promise.resolve({ management_token: 'management-2', rezerwacja: reservation('odwolana') })
    }
    return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
  })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('RezerwacjaWidget R5a', () => {
  it('po powrocie bez ważnego cookie zatrzymuje polling i pokazuje drogę odzyskania', async () => {
    vi.useFakeTimers()
    window.history.replaceState({}, '', '/?rezerwuj&platnosc=powrot')
    const expired = Object.assign(new Error('Sesja wygasła'), { status: 400 })
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path === '/online/zarzadzanie/platnosc') return Promise.reject(expired)
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<RezerwacjaWidget />)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByRole('alert')).toHaveTextContent('Ta sesja płatności nie jest już dostępna')
    const statusCalls = () => apiMock.mock.calls.filter(([path]) => (
      path === '/online/zarzadzanie/platnosc'
    )).length
    expect(statusCalls()).toBe(1)

    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(statusCalls()).toBe(1)
  })

  it('po powrocie zarządza rezerwacją przez HttpOnly cookie bez tokenu w storage lub nagłówku', async () => {
    window.history.replaceState({}, '', '/?rezerwuj&platnosc=powrot')
    sessionStorage.setItem('lokalo:public-payment:v2', JSON.stringify({
      expiresAt: Date.now() + 60_000,
      reservation: reservation(),
      payment: { id: 41, status: 'oczekuje', refund_status: 'brak' },
    }))
    let cancelled = false
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path === '/online/zarzadzanie/platnosc' && method === 'GET') {
        return Promise.resolve({
          rezerwacja: reservation(),
          platnosc: {
            id: 41,
            status: 'oplacona',
            refund_status: cancelled ? 'oczekuje' : 'brak',
            amount_minor: 5000,
          },
        })
      }
      if (path === '/online/zarzadzanie/odwolaj' && method === 'POST') {
        cancelled = true
        return Promise.resolve({
          ...reservation('odwolana'),
          platnosc: { id: 41, status: 'oplacona', refund_status: 'oczekuje', amount_minor: 5000 },
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<RezerwacjaWidget />)
    expect(await screen.findByRole('heading', { name: 'Zadatek opłacony' })).toBeInTheDocument()
    expect(JSON.stringify(sessionStorage)).not.toContain('management_token')

    fireEvent.click(screen.getByRole('button', { name: 'Odwołaj rezerwację' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/zarzadzanie/odwolaj',
      'POST',
      null,
      expect.objectContaining({
        credentials: 'include',
        headers: expect.not.objectContaining({ 'X-Reservation-Token': expect.anything() }),
      }),
    ))
    expect(await screen.findByRole('heading', { name: 'Zwrot jest przetwarzany' })).toBeInTheDocument()
  })

  it('pokazuje wynik płatności także wtedy, gdy nowe rezerwacje online są wyłączone', async () => {
    window.history.replaceState({}, '', '/?rezerwuj&platnosc=powrot')
    sessionStorage.setItem('lokalo:public-payment:v2', JSON.stringify({
      expiresAt: Date.now() + 60_000,
      reservation: reservation(),
      payment: { id: 41, status: 'oczekuje', refund_status: 'brak' },
    }))
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') {
        return Promise.resolve({ ...CONFIG_V2, ready: false })
      }
      if (path === '/online/zarzadzanie/platnosc' && method === 'GET') {
        return Promise.resolve({
          rezerwacja: reservation(),
          platnosc: {
            id: 41,
            status: 'oplacona',
            refund_status: 'brak',
            amount_minor: 5000,
          },
        })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<RezerwacjaWidget />)

    expect(await screen.findByRole('heading', { name: 'Zadatek opłacony' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', {
      name: 'Rezerwacje online są chwilowo niedostępne',
    })).not.toBeInTheDocument()
  })

  it('nie ogłasza sukcesu przed webhookiem i prowadzi do bezpiecznego checkoutu', async () => {
    const payment = {
      id: 41,
      status: 'oczekuje',
      kind: 'deposit',
      amount_minor: 10000,
      currency: 'pln',
      checkout_url: 'https://checkout.stripe.test/cs_test_41',
      po_niepowodzeniu: 'ponow',
    }
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.startsWith('/online/dostepnosc')) return Promise.resolve({ sloty: [{ godz_od: '18:00', dostepny: true }] })
      if (path === '/online/hold' && method === 'POST') return Promise.resolve({
        hold_token: 'hold-payment',
        expires_at: new Date(Date.now() + 600_000).toISOString(),
        rezerwacja: reservation(),
      })
      if (path === '/online/hold' && method === 'DELETE') return Promise.resolve(null)
      if (path === '/online/rezerwacja' && method === 'POST') return Promise.resolve({
        management_token: 'management-payment',
        rezerwacja: reservation(),
        platnosc: payment,
      })
      if (path === '/online/zarzadzanie/platnosc' && method === 'GET') return Promise.resolve({ platnosc: payment })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    await renderReadyWidget()
    await searchFor()
    fireEvent.click(await screen.findByRole('button', { name: 'Wybierz godzinę 18:00' }))
    await screen.findByRole('heading', { name: 'Dokończ rezerwację' })
    fillRequiredGuestData()
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź rezerwację' }))

    expect(await screen.findByRole('heading', { name: 'Opłać zadatek' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Dokończ rezerwację' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Rezerwacja potwierdzona' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Przejdź do bezpiecznej płatności' }))
      .toHaveAttribute('href', payment.checkout_url)
    expect(JSON.stringify(sessionStorage)).not.toContain('Jan Kowalski')
  })

  it('realizuje flow v2 z holdem, wymaganym notice i sesją zarządzania HttpOnly', async () => {
    await renderReadyWidget()
    await searchFor()
    fireEvent.click(await screen.findByRole('button', { name: 'Wybierz godzinę 18:00' }))

    const detailsHeading = await screen.findByRole('heading', { name: 'Dokończ rezerwację' })
    await waitFor(() => expect(detailsHeading).toHaveFocus())
    expect(screen.getByTestId('hold-countdown')).toHaveTextContent('10:00')
    expect(screen.getByTestId('reservation-contact-fields').className.split(' ')).toContain('sm:grid-cols-2')
    expect(screen.getByTestId('reservation-contact-fields').className.split(' ')).not.toContain('grid-cols-2')

    fillRequiredGuestData()
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź rezerwację' }))

    expect(await screen.findByRole('heading', { name: 'Rezerwacja potwierdzona' })).toBeInTheDocument()
    const createCall = apiMock.mock.calls.find(([path, method]) => path === '/online/rezerwacja' && method === 'POST')
    expect(createCall[2]).toMatchObject({
      privacy_notice_version: 'privacy-2026-07',
      privacy_notice_acknowledged: true,
      marketing_consent: false,
      marketing_consent_version: null,
      sensitive_data: null,
      sensitive_data_consent: false,
      sensitive_data_consent_version: null,
    })
    expect(createCall[2]).not.toHaveProperty('hold_token')
    expect(JSON.stringify(createCall[2])).not.toContain('hold-secret')
    expect(createCall[3]).toEqual(expect.objectContaining({
      headers: expect.objectContaining({
        'X-Reservation-Session': expect.stringMatching(/^reservation-session-/),
        'X-Reservation-Hold': 'hold-secret',
        'Idempotency-Key': expect.stringMatching(/^online-reservation-/),
      }),
    }))
    expect(document.body).not.toHaveTextContent('management-1')

    fireEvent.click(screen.getByRole('button', { name: 'Odwołaj rezerwację' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/online/zarzadzanie/odwolaj',
      'POST',
      null,
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({
          'X-Reservation-Session': expect.stringMatching(/^reservation-session-/),
        }),
      }),
    ))
    const cancelCall = apiMock.mock.calls.find(([path, method]) => (
      path === '/online/zarzadzanie/odwolaj' && method === 'POST'
    ))
    expect(cancelCall[3].headers).not.toHaveProperty('X-Reservation-Token')
    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('Termin zostanie zwolniony'),
      expect.objectContaining({ title: 'Odwołać rezerwację?' }),
    )
    expect(await screen.findByRole('heading', { name: 'Rezerwacja odwołana' })).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('management-2')
  })

  it('po błędzie konfiguracji zatrzymuje widget i pozwala bezpiecznie ponowić próbę', async () => {
    let configAttempts = 0
    apiMock.mockImplementation((path) => {
      if (path !== '/online/widget-config') return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
      configAttempts += 1
      if (configAttempts === 1) {
        return Promise.reject(Object.assign(new Error('Brak połączenia'), { status: 503 }))
      }
      return Promise.resolve(CONFIG_V2)
    })

    render(<RezerwacjaWidget />)
    expect(await screen.findByRole('heading', { name: 'Nie udało się uruchomić rezerwacji' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Brak połączenia. Sprawdź połączenie i spróbuj ponownie.')
    expect(screen.queryByRole('button', { name: 'Pokaż wolne godziny' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))
    expect(await screen.findByRole('heading', { name: 'Znajdź stolik' })).toBeInTheDocument()
    expect(configAttempts).toBe(2)
  })

  it('traktuje brak konfiguracji 404 jako świadomie wyłączone rezerwacje online', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') {
        return Promise.reject(Object.assign(new Error('Nie znaleziono konfiguracji'), { status: 404 }))
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<RezerwacjaWidget />)

    expect(await screen.findByRole('heading', {
      name: 'Rezerwacje online są chwilowo niedostępne',
    })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Nie udało się uruchomić rezerwacji' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Spróbuj ponownie' })).not.toBeInTheDocument()
  })

  it('nie uruchamia formularza po otrzymaniu starego kontraktu v1', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') return Promise.resolve({ version: 1, ready: true })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<RezerwacjaWidget />)
    expect(await screen.findByRole('heading', { name: 'Nie udało się uruchomić rezerwacji' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pokaż wolne godziny' })).not.toBeInTheDocument()
  })

  it('pokazuje alternatywy i zapisuje na waitlistę bez wymuszania marketingu', async () => {
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.startsWith('/online/dostepnosc')) return Promise.resolve({ sloty: [] })
      if (path === '/online/popyt/odrzucony' && method === 'POST') {
        return Promise.reject(new Error('Telemetria chwilowo niedostępna'))
      }
      if (path.startsWith('/online/alternatywy')) {
        return Promise.resolve({ alternatywy: [{ data: '2035-07-17', godz_od: '19:00', serwis: 'Kolacja' }] })
      }
      if (path === '/online/lista-oczekujacych' && method === 'POST') {
        return Promise.resolve({ wpis: { ...reservation('oczekuje'), godz_od: null } })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    await renderReadyWidget()
    await searchFor()
    expect(await screen.findByRole('button', { name: /17 lipca.*19:00/i })).toBeInTheDocument()
    const demandCall = apiMock.mock.calls.find(([path, method]) => path === '/online/popyt/odrzucony' && method === 'POST')
    expect(demandCall[2]).toEqual({ data: '2035-07-16', liczba_osob: 2 })
    expect(demandCall[3]).toMatchObject({
      credentials: 'include',
      keepalive: true,
      sessionHandling: false,
      headers: {
        'X-Reservation-Session': expect.any(String),
        'Idempotency-Key': 'online-rejected-demand-1',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dołącz do listy oczekujących' }))
    expect(await screen.findByRole('heading', { name: 'Lista oczekujących' })).toBeInTheDocument()

    fillRequiredGuestData()
    fireEvent.click(screen.getByRole('button', { name: 'Dołącz do listy' }))
    expect(await screen.findByRole('heading', { name: 'Jesteś na liście oczekujących' })).toBeInTheDocument()
    const waitlistCall = apiMock.mock.calls.find(([path, method]) => path === '/online/lista-oczekujacych' && method === 'POST')
    expect(waitlistCall[2]).toMatchObject({
      godz_od: null,
      privacy_notice_acknowledged: true,
      marketing_consent: false,
      sensitive_data: null,
    })
  })

  it('nie zapisuje odrzuconego popytu, gdy zwrócono wolny slot', async () => {
    await renderReadyWidget()
    await searchFor()

    expect(await screen.findByRole('button', { name: 'Wybierz godzinę 18:00' })).toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path]) => path === '/online/popyt/odrzucony')).toBe(false)
  })

  it('nie uruchamia niegotowego wariantu v2 i pokazuje bezpieczny stan niedostępności', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') return Promise.resolve({ ...CONFIG_V2, ready: false })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    render(<RezerwacjaWidget />)
    expect(await screen.findByRole('heading', { name: 'Rezerwacje online są chwilowo niedostępne' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pokaż wolne godziny' })).not.toBeInTheDocument()
  })

  it('wymaga osobnej zgody wyłącznie po podaniu danych wrażliwych i zachowuje szkic po błędzie', async () => {
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.startsWith('/online/dostepnosc')) return Promise.resolve({ sloty: [{ godz_od: '18:00', dostepny: true }] })
      if (path === '/online/hold' && method === 'POST') return Promise.resolve({
        hold_token: 'hold-sensitive',
        expires_at: new Date(Date.now() + 600_000).toISOString(),
        rezerwacja: reservation(),
      })
      if (path === '/online/hold' && method === 'DELETE') return Promise.resolve(null)
      if (path === '/online/rezerwacja' && method === 'POST') return Promise.reject(new Error('Chwilowy błąd zapisu'))
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    await renderReadyWidget()
    await searchFor()
    fireEvent.click(await screen.findByRole('button', { name: 'Wybierz godzinę 18:00' }))
    await screen.findByRole('heading', { name: 'Dokończ rezerwację' })
    fillRequiredGuestData()
    fireEvent.change(screen.getByLabelText(/Alergie lub szczególne potrzeby/), { target: { value: 'Alergia na orzechy' } })
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź rezerwację' }))

    expect(await screen.findByText('Potwierdź zgodę na przetwarzanie podanych danych wrażliwych.')).toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path, method]) => path === '/online/rezerwacja' && method === 'POST')).toBe(false)

    fireEvent.click(screen.getByLabelText(/Zgadzam się na wykorzystanie podanych informacji/))
    fireEvent.click(screen.getByRole('button', { name: 'Potwierdź rezerwację' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Chwilowy błąd zapisu')
    expect(screen.getByLabelText('Imię i nazwisko')).toHaveValue('Jan Kowalski')
    expect(screen.getByLabelText(/Alergie lub szczególne potrzeby/)).toHaveValue('Alergia na orzechy')
  })

  it('anuluje stare wyszukiwanie i nie pokazuje jego spóźnionej odpowiedzi', async () => {
    const first = deferred()
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.includes('data=2035-07-16')) return first.promise
      if (path.includes('data=2035-07-17')) return Promise.resolve({ sloty: [{ godz_od: '19:00', dostepny: true }] })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    await renderReadyWidget()
    await searchFor({ date: '2035-07-16' })
    fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2035-07-17' } })
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż wolne godziny' }))
    expect(await screen.findByRole('button', { name: 'Wybierz godzinę 19:00' })).toBeInTheDocument()

    await act(async () => first.resolve({ sloty: [{ godz_od: '18:00', dostepny: true }] }))
    expect(screen.queryByRole('button', { name: 'Wybierz godzinę 18:00' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wybierz godzinę 19:00' })).toBeInTheDocument()
  })

  it('rozróżnia błąd dostępności od pustego dnia i oferuje lokalny retry', async () => {
    apiMock.mockImplementation((path) => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.startsWith('/online/dostepnosc')) return Promise.reject(new Error('Brak połączenia z lokalem'))
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${path}`))
    })

    await renderReadyWidget()
    await searchFor()
    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z lokalem')
    expect(screen.getByRole('button', { name: 'Spróbuj ponownie' })).toHaveClass('min-h-11')
    expect(screen.queryByText('Ten dzień jest już pełny')).not.toBeInTheDocument()
  })

  it('wygasza hold, zwalnia go i zachowuje wpisany formularz', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2035-07-16T16:00:00.000Z'))
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/online/widget-config') return Promise.resolve(CONFIG_V2)
      if (path.startsWith('/online/dostepnosc')) return Promise.resolve({ sloty: [{ godz_od: '18:00', dostepny: true }] })
      if (path === '/online/hold' && method === 'POST') return Promise.resolve({
        hold_token: 'expiring-hold',
        expires_at: '2035-07-16T16:00:02.000Z',
        rezerwacja: reservation(),
      })
      if (path === '/online/hold' && method === 'DELETE') return Promise.resolve(null)
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<RezerwacjaWidget />)
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    fireEvent.change(screen.getByLabelText('Data'), { target: { value: '2035-07-16' } })
    fireEvent.click(screen.getByRole('button', { name: 'Pokaż wolne godziny' }))
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: 'Wybierz godzinę 18:00' }))
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    fireEvent.change(screen.getByLabelText('Imię i nazwisko'), { target: { value: 'Zachowany Gość' } })

    await act(async () => vi.advanceTimersByTime(2_100))
    expect(screen.getByRole('alert')).toHaveTextContent('Czas na dokończenie rezerwacji minął')
    expect(screen.getByLabelText('Imię i nazwisko')).toHaveValue('Zachowany Gość')
    expect(screen.getByRole('button', { name: 'Potwierdź rezerwację' })).toBeDisabled()
    expect(apiMock).toHaveBeenCalledWith(
      '/online/hold',
      'DELETE',
      null,
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-Reservation-Session': expect.any(String),
          'X-Reservation-Hold': 'expiring-hold',
        }),
      }),
    )
  })

  it('ma semantyczny, mobilnie układany formularz i kontrolki o celu co najmniej 44 px', async () => {
    await renderReadyWidget()
    expect(document.querySelector('main')).toBeInTheDocument()
    expect(screen.getByTestId('reservation-search-fields').className.split(' ')).toContain('sm:grid-cols-2')
    expect(screen.getByTestId('reservation-search-fields').className.split(' ')).not.toContain('grid-cols-2')
    expect(screen.getByLabelText('Data')).toHaveClass('min-h-12')
    expect(screen.getByLabelText('Liczba osób')).toHaveAttribute('inputmode', 'numeric')
    expect(screen.getByRole('button', { name: 'Pokaż wolne godziny' })).toHaveClass('min-h-12')
    expect(screen.getByRole('status', { hidden: true })).toHaveAttribute('aria-live', 'polite')
  })
})
