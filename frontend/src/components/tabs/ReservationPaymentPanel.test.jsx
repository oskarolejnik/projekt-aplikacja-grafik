// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, keyMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  keyMock: vi.fn(() => 'stable-payment-key'),
}))

vi.mock('../../lib/api', () => ({ api: apiMock, nowyKluczIdempotencji: keyMock }))
vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span data-icon={name} aria-hidden /> }))

import ReservationPaymentPanel from './ReservationPaymentPanel'

const PAYMENT = {
  id: 18,
  termin_id: 7,
  status: 'oplacona',
  rodzaj: 'zadatek',
  kwota_minor: 10_000,
  przechwycono_minor: 10_000,
  zwrocono_minor: 0,
  waluta: 'PLN',
  refund_status: 'brak',
  provider: 'stripe',
}

const COMMAND = {
  id: 31,
  platnosc_id: PAYMENT.id,
  typ: 'capture',
  stan: 'queued',
}

const flushPromises = async () => {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
  })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  keyMock.mockReturnValue('stable-payment-key')
})

describe('ReservationPaymentPanel', () => {
  it('pokazuje kanoniczny status i zleca pełny zwrot dopiero po potwierdzeniu', async () => {
    const confirmAction = vi.fn().mockResolvedValue(true)
    apiMock.mockImplementation((path, method) => {
      if (path === '/platnosci?termin_id=7' && method === 'GET') return Promise.resolve([PAYMENT])
      if (path === '/platnosci/18/zwrot' && method === 'POST') {
        return Promise.resolve({ payment: { ...PAYMENT, refund_status: 'oczekuje' } })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={confirmAction} />)

    expect(await screen.findByText('Opłacona')).toBeInTheDocument()
    expect(screen.getByText('100,00 zł')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Zwróć zadatek' }))

    await waitFor(() => expect(confirmAction).toHaveBeenCalled())
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/platnosci/18/zwrot',
      'POST',
      { powod: 'requested_by_customer' },
      { headers: { 'Idempotency-Key': 'stable-payment-key' } },
    ))
    expect(await screen.findByText('Zwrot jest przetwarzany.')).toBeInTheDocument()
    expect(screen.getByText('Operacja w toku')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Zwróć zadatek' })).not.toBeInTheDocument()
    expect(screen.getByText('Zlecono pełny zwrot.')).toBeInTheDocument()
  })

  it('dla preautoryzacji rozdziela pobranie od zwolnienia blokady', async () => {
    apiMock.mockResolvedValue([{ ...PAYMENT, status: 'autoryzowana', rodzaj: 'preautoryzacja' }])

    render(<ReservationPaymentPanel reservationId={7} confirmAction={vi.fn()} />)

    expect(await screen.findByText('Kwota zablokowana')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pobierz kwotę' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Zwolnij blokadę' })).toBeInTheDocument()
    expect(screen.getByText(/Środki są tylko zablokowane/)).toBeInTheDocument()
  })

  it('nie sugeruje płatności, gdy polityka jej nie wymaga', async () => {
    const onManagedPaymentChange = vi.fn()
    apiMock.mockResolvedValue([])

    render(
      <ReservationPaymentPanel
        reservationId={7}
        confirmAction={vi.fn()}
        onManagedPaymentChange={onManagedPaymentChange}
      />,
    )

    expect(await screen.findByText('Ta rezerwacja nie wymaga płatności online.')).toBeInTheDocument()
    expect(onManagedPaymentChange).toHaveBeenLastCalledWith(false)
  })

  it('pozwala ręcznie potwierdzić wyłącznie płatność demonstracyjną', async () => {
    const sandbox = { ...PAYMENT, status: 'oczekuje', provider: 'sandbox', link: '/?platnosc=sandbox' }
    apiMock.mockImplementation((path, method) => {
      if (method === 'GET') return Promise.resolve([sandbox])
      if (path === '/platnosci/18/oplacona' && method === 'POST') return Promise.resolve(PAYMENT)
      return Promise.reject(new Error('unexpected'))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Potwierdź demo' }))

    expect(await screen.findByText('Oznaczono płatność demonstracyjną jako opłaconą.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/platnosci/18/oplacona', 'POST')
  })

  it('pokazuje należność no-show jako ręczne rozliczenie bez pollingu', async () => {
    vi.useFakeTimers()
    const ledger = {
      ...PAYMENT,
      status: 'oczekuje',
      rodzaj: 'no_show',
      provider: 'ledger',
      link: null,
    }
    apiMock.mockImplementation((path, method) => {
      if (method === 'GET') return Promise.resolve([ledger])
      if (path === '/platnosci/18/oplacona' && method === 'POST') {
        return Promise.resolve({ ...ledger, status: 'oplacona' })
      }
      return Promise.reject(new Error('unexpected'))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={vi.fn()} />)
    await flushPromises()

    expect(screen.getByText('Opłata za nieobecność')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Oznacz jako rozliczoną' }))
    await flushPromises()
    expect(screen.getByText('Oznaczono należność jako rozliczoną.')).toBeInTheDocument()

    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('pokazuje wszystkie płatności i wykonuje działania wyłącznie dla wybranej pozycji', async () => {
    const confirmAction = vi.fn().mockResolvedValue(true)
    const ledger = {
      ...PAYMENT,
      id: 19,
      status: 'oczekuje',
      rodzaj: 'no_show',
      kwota_minor: 3_500,
      provider: 'ledger',
      latest_command: null,
    }
    const authorized = {
      ...PAYMENT,
      status: 'autoryzowana',
      rodzaj: 'preautoryzacja',
      latest_command: { ...COMMAND, stan: 'succeeded' },
    }
    apiMock.mockImplementation((path, method) => {
      if (path === '/platnosci?termin_id=7' && method === 'GET') {
        return Promise.resolve([ledger, authorized])
      }
      if (path === '/platnosci/18/capture' && method === 'POST') {
        return Promise.resolve({ payment: authorized, command: COMMAND })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={confirmAction} />)

    const ledgerRow = await screen.findByRole('radio', {
      name: /Opłata za nieobecność.*Oczekuje na płatność/,
    })
    const authorizationRow = screen.getByRole('radio', {
      name: /Preautoryzacja.*Kwota zablokowana, Operacja zakończona/,
    })
    expect(ledgerRow).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: 'Oznacz jako rozliczoną' })).toBeInTheDocument()
    expect(screen.getByText(/Operacja zakończona/)).toBeInTheDocument()

    fireEvent.click(authorizationRow)

    expect(authorizationRow).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByRole('button', { name: 'Oznacz jako rozliczoną' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pobierz kwotę' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/platnosci/18/capture',
      'POST',
      { powod: 'operator_capture' },
      { headers: { 'Idempotency-Key': 'stable-payment-key' } },
    ))
    expect(apiMock.mock.calls.some(([path]) => path === '/platnosci/19/capture')).toBe(false)
  })

  it('zachowuje polecenie, blokuje kolejne akcje i kończy polling po stanie terminalnym', async () => {
    vi.useFakeTimers()
    const authorized = { ...PAYMENT, status: 'autoryzowana', rodzaj: 'preautoryzacja' }
    let listReads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/platnosci?termin_id=7' && method === 'GET') {
        listReads += 1
        return Promise.resolve([listReads === 1 ? authorized : PAYMENT])
      }
      if (path === '/platnosci/18/capture' && method === 'POST') {
        return Promise.resolve({ payment: authorized, command: COMMAND })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={vi.fn().mockResolvedValue(true)} />)
    await flushPromises()

    fireEvent.click(screen.getByRole('button', { name: 'Pobierz kwotę' }))
    await flushPromises()

    expect(screen.getByText('Operacja w toku')).toBeInTheDocument()
    expect(screen.getByText(/Pobranie kwoty jest w toku/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pobierz kwotę' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Zwolnij blokadę' })).toBeDisabled()
    expect(listReads).toBe(1)

    await act(async () => vi.advanceTimersByTimeAsync(1_999))
    expect(listReads).toBe(1)
    await act(async () => vi.advanceTimersByTimeAsync(1))

    expect(listReads).toBe(2)
    expect(screen.getByText('Opłacona')).toBeInTheDocument()
    expect(screen.queryByText('Operacja w toku')).not.toBeInTheDocument()

    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(listReads).toBe(2)
  })

  it('pauzuje odświeżanie w ukrytej karcie i zatrzymuje je po odmontowaniu', async () => {
    vi.useFakeTimers()
    const waiting = {
      ...PAYMENT,
      status: 'oczekuje',
      przechwycono_minor: 0,
      link: 'https://checkout.stripe.test/session',
    }
    apiMock.mockResolvedValue([waiting])

    const { unmount } = render(
      <ReservationPaymentPanel reservationId={7} confirmAction={vi.fn()} />,
    )
    await flushPromises()
    expect(apiMock).toHaveBeenCalledTimes(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(apiMock).toHaveBeenCalledTimes(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(apiMock).toHaveBeenCalledTimes(2)

    unmount()
    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(apiMock).toHaveBeenCalledTimes(2)
  })

  it('odtwarza terminalny stan polecenia po ponownym otwarciu panelu', async () => {
    vi.useFakeTimers()
    const authorized = {
      ...PAYMENT,
      status: 'autoryzowana',
      rodzaj: 'preautoryzacja',
      latest_command: { ...COMMAND, stan: 'uncertain' },
    }
    apiMock.mockResolvedValue([authorized])

    render(<ReservationPaymentPanel reservationId={7} confirmAction={vi.fn()} />)
    await flushPromises()

    expect(screen.getByText('Wymaga uzgodnienia')).toBeInTheDocument()
    expect(screen.getByText(/bez drugiego obciążenia/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sprawdź stan u operatora' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Pobierz kwotę' })).toBeDisabled()

    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(apiMock).toHaveBeenCalledTimes(1)
  })

  it('uzgadnia wybraną niepewną płatność i polluje nową komendę do potwierdzenia', async () => {
    vi.useFakeTimers()
    const confirmAction = vi.fn().mockResolvedValue(true)
    const ledger = {
      ...PAYMENT,
      id: 19,
      status: 'oplacona',
      rodzaj: 'no_show',
      kwota_minor: 3_500,
      provider: 'ledger',
      latest_command: null,
    }
    const uncertain = {
      ...PAYMENT,
      status: 'autoryzowana',
      rodzaj: 'preautoryzacja',
      latest_command: { ...COMMAND, stan: 'uncertain' },
    }
    const reconcileCommand = {
      ...COMMAND,
      id: 44,
      typ: 'reconcile',
      stan: 'queued',
    }
    let listReads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/platnosci?termin_id=7' && method === 'GET') {
        listReads += 1
        return Promise.resolve(listReads === 1
          ? [ledger, uncertain]
          : [ledger, {
            ...uncertain,
            status: 'oplacona',
            latest_command: { ...reconcileCommand, stan: 'succeeded' },
          }])
      }
      if (path === '/platnosci/18/reconcile' && method === 'POST') {
        return Promise.resolve({ payment: uncertain, command: reconcileCommand })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationPaymentPanel reservationId={7} confirmAction={confirmAction} />)
    await flushPromises()
    fireEvent.click(screen.getByRole('radio', { name: /Preautoryzacja.*Wymaga uzgodnienia/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź stan u operatora' }))
    await flushPromises()

    expect(confirmAction).toHaveBeenCalledWith(
      expect.stringMatching(/nie utworzy drugiego obciążenia ani zwrotu/),
      expect.objectContaining({ title: 'Sprawdź stan', confirmText: 'Sprawdź stan' }),
    )
    expect(apiMock).toHaveBeenCalledWith(
      '/platnosci/18/reconcile',
      'POST',
      { powod: 'operator_reconcile' },
      { headers: { 'Idempotency-Key': 'stable-payment-key' } },
    )
    expect(screen.getByText('Operacja w toku')).toBeInTheDocument()
    expect(screen.getByText(/Oczekuje w kolejce/)).toBeInTheDocument()
    expect(listReads).toBe(1)

    await act(async () => vi.advanceTimersByTimeAsync(2_000))
    expect(listReads).toBe(2)
    expect(screen.getAllByText('Opłacona').length).toBeGreaterThan(0)
    expect(screen.queryByText('Operacja w toku')).not.toBeInTheDocument()

    await act(async () => vi.advanceTimersByTimeAsync(120_000))
    expect(listReads).toBe(2)
  })
})
