// @vitest-environment jsdom
import { StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, keyMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  keyMock: vi.fn(() => 'stable-communication-key'),
}))

vi.mock('../../lib/api', () => ({ api: apiMock, nowyKluczIdempotencji: keyMock }))
vi.mock('../../lib/icons', () => ({ Icon: ({ name }) => <span data-icon={name} aria-hidden /> }))

import ReservationCommunicationPanel from './ReservationCommunicationPanel'

const MESSAGE = {
  id: 91,
  event: 'confirmation',
  event_label: 'Potwierdzenie',
  channel: 'email',
  recipient: 'n***@example.com',
  state: 'failed',
  attention_required: true,
  attempt_count: 2,
  max_attempts: 5,
  created_at: '2030-01-02T17:00:00Z',
  updated_at: '2030-01-02T17:05:00Z',
  last_error_code: 'SMTP_UNAVAILABLE',
  attempts: [],
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  keyMock.mockReturnValue('stable-communication-key')
  vi.useRealTimers()
})

describe('ReservationCommunicationPanel', () => {
  it('kończy odczyt historii po kontrolnym replayu efektów w StrictMode', async () => {
    apiMock.mockResolvedValue({ summary: null, messages: [] })

    render(
      <StrictMode>
        <ReservationCommunicationPanel ownerType="reservation" ownerId={7} />
      </StrictMode>,
    )

    expect(await screen.findByText('Nie ma jeszcze wiadomości dla tej rezerwacji.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik/7/komunikacja',
      'GET',
      null,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('kolejkuje potwierdzenie i nie obiecuje wysyłki synchronicznej', async () => {
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        return Promise.resolve(historyLoads === 1
          ? { summary: null, messages: [] }
          : { summary: { state: 'queued', channel: 'email' }, messages: [{ ...MESSAGE, state: 'queued', attempt_count: 0 }] })
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        return Promise.resolve({ queued: 1, messages: [{ ...MESSAGE, state: 'queued' }] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    await screen.findByText('Nie ma jeszcze wiadomości dla tej rezerwacji.')

    const queueButton = screen.getByRole('button', { name: 'Wyślij potwierdzenie' })
    expect(queueButton).toHaveClass('min-h-11')
    fireEvent.click(queueButton)

    expect(await screen.findByText('Dodano potwierdzenie do kolejki.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik/7/wyslij-potwierdzenie',
      'POST',
      null,
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: { 'Idempotency-Key': 'stable-communication-key' },
      }),
    )
    expect(screen.queryByText('Wysłano e-mail z potwierdzeniem.')).not.toBeInTheDocument()
  })

  it('pozwala ponowić dopiero wiadomość zakończoną błędem', async () => {
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        const message = historyLoads === 1 ? MESSAGE : { ...MESSAGE, state: 'queued', attention_required: false }
        return Promise.resolve({ summary: { state: message.state, channel: message.channel }, messages: [message] })
      }
      if (path === `/rezerwacje/komunikacja/${MESSAGE.id}/retry` && method === 'POST') {
        return Promise.resolve({ ...MESSAGE, state: 'queued' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    const retryButton = await screen.findByRole('button', { name: 'Ponów' })
    expect(screen.getByRole('button', { name: 'Wyślij potwierdzenie ponownie' })).toBeDisabled()
    expect(screen.getByText(/Użyj akcji „Ponów” przy tej wiadomości/)).toBeInTheDocument()
    fireEvent.click(retryButton)

    expect(await screen.findByText('Ponowienie dodano do kolejki.')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      `/rezerwacje/komunikacja/${MESSAGE.id}/retry`,
      'POST',
      null,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Ponów' })).not.toBeInTheDocument())
  })

  it('dla niepewnego wyniku wymaga uzgodnienia i jawnie ostrzega przed duplikatem', async () => {
    const uncertain = { ...MESSAGE, state: 'uncertain', channel: 'sms', recipient: '***700' }
    let reconciled = false
    apiMock.mockImplementation((path, method, body) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        const message = reconciled ? { ...uncertain, state: 'retry', attention_required: false } : uncertain
        return Promise.resolve({ summary: { state: message.state, channel: message.channel }, messages: [message] })
      }
      if (path === `/rezerwacje/komunikacja/${MESSAGE.id}/reconcile` && method === 'POST') {
        reconciled = true
        return Promise.resolve({ ...uncertain, state: 'retry', reconciliation: body })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)

    expect(await screen.findByText(/ponowienie może wysłać duplikat/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Ponów$/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ponów mimo ryzyka' }))
    expect(await screen.findByText('Dodaj krótką notatkę z wynikiem sprawdzenia.')).toBeInTheDocument()
    expect(apiMock.mock.calls.some(([path]) => path.endsWith('/reconcile'))).toBe(false)

    fireEvent.change(screen.getByLabelText('Wynik sprawdzenia'), {
      target: { value: 'Brak wiadomości w panelu operatora SMS.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Ponów mimo ryzyka' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      `/rezerwacje/komunikacja/${MESSAGE.id}/reconcile`,
      'POST',
      { wynik: 'retry', notatka: 'Brak wiadomości w panelu operatora SMS.' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByText(/świadomą zgodą na ryzyko duplikatu/i)).toBeInTheDocument()
  })

  it('nie wysyła na stare dane kontaktowe, gdy formularz ma niezapisane zmiany', async () => {
    apiMock.mockResolvedValue({
      summary: { state: 'failed', channel: 'email' },
      messages: [MESSAGE],
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} actionsDisabled />)

    const heading = screen.getByRole('heading', { name: 'Komunikacja z gościem' })
    const section = heading.closest('section')
    expect(section).toHaveAttribute('aria-labelledby', heading.id)
    expect(await screen.findByRole('button', { name: 'Ponów' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Wyślij potwierdzenie ponownie' })).toBeDisabled()
    expect(screen.getByText('Zapisz albo cofnij zmiany w rezerwacji przed kolejną wiadomością.')).toBeInTheDocument()
  })

  it('obsługuje historię i akcję „stolik gotowy” dla listy oczekujących', async () => {
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/lista-oczekujacych/11/komunikacja' && method === 'GET') {
        historyLoads += 1
        return Promise.resolve(historyLoads === 1
          ? { summary: null, messages: [] }
          : {
              summary: { state: 'queued', channel: 'sms' },
              messages: [{ ...MESSAGE, event: 'table_ready', event_label: 'Stolik gotowy', channel: 'sms', state: 'queued' }],
            })
      }
      if (path === '/lista-oczekujacych/11/powiadom' && method === 'POST') {
        return Promise.resolve({ queued: true, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="waitlist" ownerId={11} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Powiadom: stolik gotowy' }))

    expect(await screen.findByText('Dodano powiadomienie „stolik gotowy” do kolejki.')).toBeInTheDocument()
    expect(screen.getByText('Stolik gotowy')).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/lista-oczekujacych/11/powiadom',
      'POST',
      null,
      expect.objectContaining({ headers: { 'Idempotency-Key': 'stable-communication-key' } }),
    )
  })

  it('nie oferuje ponownego „stolik gotowy” po wysłanej grupie ani legacy stampie', async () => {
    const tableReady = { ...MESSAGE, event: 'table_ready', event_label: 'Stolik gotowy', state: 'sent' }
    apiMock.mockResolvedValue({
      summary: { state: 'sent', channel: 'email' },
      messages: [tableReady],
    })

    const { rerender } = render(<ReservationCommunicationPanel ownerType="waitlist" ownerId={11} />)

    const sentButton = await screen.findByRole('button', { name: 'Powiadom: stolik gotowy' })
    expect(sentButton).toBeDisabled()
    expect(screen.getByText(/Gość został już powiadomiony o gotowym stoliku/)).toBeInTheDocument()

    apiMock.mockResolvedValue({ summary: null, messages: [] })
    rerender(<ReservationCommunicationPanel ownerType="waitlist" ownerId={12} manualAlreadyHandled />)
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/lista-oczekujacych/12/komunikacja',
      'GET',
      null,
      expect.any(Object),
    ))
    expect(screen.getByRole('button', { name: 'Powiadom: stolik gotowy' })).toBeDisabled()
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('rozpoznaje legacy powiadomienie z podsumowania API bez lokalnego stempla', async () => {
    apiMock.mockResolvedValue({
      summary: { state: 'sent', channel: 'sms', event: 'table_ready', legacy_delivery: true },
      messages: [],
      legacy_delivery: true,
    })

    render(<ReservationCommunicationPanel ownerType="waitlist" ownerId={13} />)

    const button = await screen.findByRole('button', { name: 'Powiadom: stolik gotowy' })
    expect(button).toBeDisabled()
    expect(screen.getByText(/Gość został już powiadomiony o gotowym stoliku/)).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('blokuje aktywny duplikat bez kolejnego POST', async () => {
    apiMock.mockResolvedValue({
      summary: { state: 'queued', channel: 'email' },
      messages: [{ ...MESSAGE, state: 'queued' }],
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)

    const button = await screen.findByRole('button', { name: 'Wyślij potwierdzenie ponownie' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Potwierdzenie jest już w kolejce.')).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('respektuje zagregowany błąd grupy, nawet gdy jej pierwszy wiersz jest wysłany', async () => {
    apiMock.mockResolvedValue({
      summary: { state: 'failed', event: 'confirmation', channel: 'oba', attention_count: 1 },
      messages: [
        { ...MESSAGE, id: 92, state: 'sent', channel: 'email', attention_required: false },
        { ...MESSAGE, id: 91, state: 'failed', channel: 'sms' },
      ],
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)

    const resend = await screen.findByRole('button', { name: 'Wyślij potwierdzenie ponownie' })
    expect(resend).toBeDisabled()
    expect(screen.getByText(/Poprzednia wiadomość nie została dostarczona/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ponów' })).toBeEnabled()
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('blokuje duplikat na podstawie snapshotu, gdy odczyt historii zawiedzie', async () => {
    apiMock.mockRejectedValue(new Error('Historia chwilowo niedostępna.'))

    render(
      <ReservationCommunicationPanel
        ownerType="reservation"
        ownerId={7}
        initialSummary={{ state: 'queued', event: 'confirmation', channel: 'email' }}
      />,
    )

    expect(await screen.findByText('Historia chwilowo niedostępna.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Wyślij potwierdzenie ponownie' })
    expect(button).toBeDisabled()
    expect(screen.getByRole('status', { name: 'W kolejce, e-mail' })).toBeInTheDocument()
    expect(screen.getByText(/Najpierw ponów odczyt historii/)).toBeInTheDocument()
    fireEvent.click(button)
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('nie pozwala kolejkować bez udanego pierwszego odczytu historii', async () => {
    apiMock.mockRejectedValue(new Error('Nie udało się sprawdzić historii.'))

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)

    expect(await screen.findByText('Nie udało się sprawdzić historii.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Wyślij potwierdzenie' })
    expect(button).toBeDisabled()
    expect(screen.getByText(/Najpierw ponów odczyt historii/)).toBeInTheDocument()
    fireEvent.click(button)
    expect(apiMock.mock.calls.filter(([, method]) => method === 'POST')).toHaveLength(0)
  })

  it('przed ponowną wysyłką pyta świadomie i zachowuje Idempotency-Key po błędzie sieci', async () => {
    const confirmAction = vi.fn().mockResolvedValue(true)
    let postAttempts = 0
    const sent = { ...MESSAGE, state: 'sent', attention_required: false }
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        return Promise.resolve({ summary: { state: 'sent', channel: 'email' }, messages: [sent] })
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        postAttempts += 1
        return postAttempts === 1
          ? Promise.reject(new Error('Niepewne połączenie.'))
          : Promise.resolve({ queued: 1, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} confirmAction={confirmAction} />)
    const resend = await screen.findByRole('button', { name: 'Wyślij potwierdzenie ponownie' })
    fireEvent.click(resend)
    expect(await screen.findByText('Niepewne połączenie.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Wyślij potwierdzenie ponownie' }))
    expect(await screen.findByText('Dodano potwierdzenie do kolejki.')).toBeInTheDocument()

    expect(confirmAction).toHaveBeenCalledTimes(2)
    expect(confirmAction).toHaveBeenCalledWith(
      expect.stringContaining('Gość może otrzymać kolejny egzemplarz'),
      expect.objectContaining({ confirmText: 'Dodaj ponownie' }),
    )
    const headers = apiMock.mock.calls
      .filter(([path, method]) => path.endsWith('/wyslij-potwierdzenie') && method === 'POST')
      .map(([, , , options]) => options.headers)
    expect(headers).toEqual([
      { 'Idempotency-Key': 'stable-communication-key', 'X-Confirm-Resend': 'true' },
      { 'Idempotency-Key': 'stable-communication-key', 'X-Confirm-Resend': 'true' },
    ])
    expect(keyMock).toHaveBeenCalledTimes(1)
  })

  it('używa kanonicznego wymogu resend dla historii mieszanej sent i expired', async () => {
    const confirmAction = vi.fn().mockResolvedValue(true)
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        return Promise.resolve(historyLoads === 1
          ? {
              manual_confirmation_state: 'expired',
              manual_confirmation_resend_required: true,
              summary: { state: 'expired', event: 'confirmation', channel: 'email' },
              messages: [
                { ...MESSAGE, id: 93, state: 'expired' },
                { ...MESSAGE, id: 92, state: 'sent', attention_required: false },
              ],
            }
          : {
              manual_confirmation_state: 'queued',
              manual_confirmation_resend_required: true,
              summary: { state: 'queued', event: 'confirmation', channel: 'email' },
              messages: [{ ...MESSAGE, id: 94, state: 'queued', attention_required: false }],
            })
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        return Promise.resolve({ queued: 1, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} confirmAction={confirmAction} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Wyślij potwierdzenie ponownie' }))

    expect(await screen.findByText('Dodano potwierdzenie do kolejki.')).toBeInTheDocument()
    expect(confirmAction).toHaveBeenCalledTimes(1)
    expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik/7/wyslij-potwierdzenie',
      'POST',
      null,
      expect.objectContaining({
        headers: {
          'Idempotency-Key': 'stable-communication-key',
          'X-Confirm-Resend': 'true',
        },
      }),
    )
  })

  it('pozwala na nową kolejkę przy kanonicznym null mimo historycznego failed bez retry', async () => {
    const confirmAction = vi.fn().mockResolvedValue(true)
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        return Promise.resolve(historyLoads === 1
          ? {
              manual_confirmation_state: null,
              manual_confirmation_resend_required: false,
              summary: { state: 'failed', event: 'confirmation', channel: 'email' },
              messages: [{ ...MESSAGE, retry_allowed: false }],
            }
          : {
              manual_confirmation_state: 'queued',
              manual_confirmation_resend_required: false,
              summary: { state: 'queued', event: 'confirmation', channel: 'email' },
              messages: [{ ...MESSAGE, id: 94, state: 'queued', attention_required: false }],
            })
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        return Promise.resolve({ queued: 1, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} confirmAction={confirmAction} />)

    const queueButton = await screen.findByRole('button', { name: 'Wyślij potwierdzenie' })
    expect(queueButton).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Ponów' })).not.toBeInTheDocument()
    expect(screen.getByText(/wcześniejszej wersji rezerwacji i nie można jej ponowić/)).toBeInTheDocument()
    fireEvent.click(queueButton)

    expect(await screen.findByText('Dodano potwierdzenie do kolejki.')).toBeInTheDocument()
    expect(confirmAction).not.toHaveBeenCalled()
    expect(apiMock).toHaveBeenCalledWith(
      '/rezerwacje-stolik/7/wyslij-potwierdzenie',
      'POST',
      null,
      expect.objectContaining({ headers: { 'Idempotency-Key': 'stable-communication-key' } }),
    )
  })

  it('po konflikcie z innej karty odczytuje stan kanoniczny i dalej go odpytuje', async () => {
    vi.useFakeTimers()
    let historyLoads = 0
    const conflict = Object.assign(new Error('Wiadomość jest już w kolejce.'), {
      status: 409,
      code: 'COMMUNICATION_ALREADY_PENDING',
    })
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        if (historyLoads === 1) {
          return Promise.resolve({
            manual_confirmation_state: null,
            manual_confirmation_resend_required: false,
            summary: null,
            messages: [],
          })
        }
        if (historyLoads === 2) {
          return Promise.resolve({
            manual_confirmation_state: 'queued',
            manual_confirmation_resend_required: false,
            summary: null,
            messages: [],
          })
        }
        return Promise.resolve({
          manual_confirmation_state: 'sent',
          manual_confirmation_resend_required: true,
          summary: { state: 'sent', event: 'confirmation', channel: 'email' },
          messages: [{ ...MESSAGE, state: 'sent', attention_required: false }],
        })
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        return Promise.reject(conflict)
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    await act(async () => {})
    fireEvent.click(screen.getByRole('button', { name: 'Wyślij potwierdzenie' }))
    await act(async () => {})

    expect(historyLoads).toBe(2)
    expect(screen.getByRole('button', { name: 'Wyślij potwierdzenie ponownie' })).toBeDisabled()
    expect(screen.getByText('Potwierdzenie jest już w kolejce.')).toBeInTheDocument()
    expect(keyMock).toHaveBeenCalledTimes(1)

    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(historyLoads).toBe(3)
  })

  it('po przyjętym POST blokuje duplikat także wtedy, gdy odczyt statusu zawiedzie', async () => {
    let historyLoads = 0
    let postAttempts = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        return historyLoads === 1
          ? Promise.resolve({ summary: null, messages: [] })
          : Promise.reject(new Error('Brak odczytu po zapisie.'))
      }
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        postAttempts += 1
        return Promise.resolve({ queued: 1, messages: [] })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Wyślij potwierdzenie' }))

    expect(await screen.findByText('Dodano potwierdzenie do kolejki.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Wyślij potwierdzenie' })
    expect(button).toBeDisabled()
    expect(screen.getByText('Potwierdzenie jest już w kolejce.')).toBeInTheDocument()
    fireEvent.click(button)
    expect(postAttempts).toBe(1)
  })

  it('zachowuje historię, gdy ciche odświeżenie chwilowo zawiedzie', async () => {
    vi.useFakeTimers()
    let historyLoads = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') {
        historyLoads += 1
        return historyLoads === 1
          ? Promise.resolve({
              summary: { state: 'queued', channel: 'email' },
              messages: [{ ...MESSAGE, state: 'queued' }],
            })
          : Promise.reject(new Error('Serwer chwilowo niedostępny.'))
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    await act(async () => {})
    expect(screen.getByText('Potwierdzenie')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })

    expect(screen.getByText('Potwierdzenie')).toBeInTheDocument()
    expect(screen.getByText('Nie udało się odświeżyć statusu: Serwer chwilowo niedostępny.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ponów odczyt' })).not.toBeInTheDocument()
  })

  it('odrzuca spóźniony wynik POST po zmianie właściciela panelu', async () => {
    let resolveOldPost
    let oldSignal
    apiMock.mockImplementation((path, method, _body, options) => {
      if (path === '/rezerwacje-stolik/7/komunikacja' && method === 'GET') return Promise.resolve({ summary: null, messages: [] })
      if (path === '/rezerwacje-stolik/8/komunikacja' && method === 'GET') return Promise.resolve({ summary: null, messages: [] })
      if (path === '/rezerwacje-stolik/7/wyslij-potwierdzenie' && method === 'POST') {
        oldSignal = options.signal
        return new Promise((resolve) => { resolveOldPost = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method} ${path}`))
    })

    const { rerender } = render(<ReservationCommunicationPanel ownerType="reservation" ownerId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Wyślij potwierdzenie' }))
    await waitFor(() => expect(resolveOldPost).toBeTypeOf('function'))

    rerender(<ReservationCommunicationPanel ownerType="reservation" ownerId={8} />)
    await waitFor(() => expect(oldSignal.aborted).toBe(true))
    expect(await screen.findByRole('button', { name: 'Wyślij potwierdzenie' })).toBeEnabled()

    await act(async () => resolveOldPost({ queued: 1, messages: [] }))
    expect(screen.queryByText('Dodano potwierdzenie do kolejki.')).not.toBeInTheDocument()
  })
})
