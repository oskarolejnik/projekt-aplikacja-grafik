// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, authState, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  authState: { isAdmin: false, showPay: false },
  toastMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    isAdmin: authState.isAdmin,
    can: (permission) => permission === 'wyplaty.podglad' && authState.showPay,
  }),
}))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import RaportGodzin from './RaportGodzin'

const RAPORT = {
  pracownicy: [{
    pracownik_id: 3,
    pracownik: 'Jan Nowak',
    dzial: 'sala',
    suma_godzin: 8,
    do_wyplaty: 987654.32,
    do_wyplaty_po_zaliczkach: 987654.32,
    zaliczki_kwota: 0,
    stanowiska: [{ stanowisko: 'Kelner', godziny: 8, stawka: 1234.56, kwota: 987654.32 }],
  }],
  stanowiska_podsumowanie: [{ stanowisko: 'Kelner', godziny: 8, kwota: 987654.32 }],
  zaoszczedzone: { godziny: 1, kwota: 543210.98 },
  niedopasowani_rcp: [],
  duze_ciecia: [],
  male_ciecia: [],
  na_zmianie: [],
}

const RAPORT_BEZ_KWOT = {
  pracownicy: [{
    pracownik_id: 3,
    pracownik: 'Jan Nowak',
    dzial: 'sala',
    suma_godzin: 8,
    stanowiska: [{ stanowisko: 'Kelner', godziny: 8 }],
  }],
  stanowiska_podsumowanie: [{ stanowisko: 'Kelner', godziny: 8 }],
  zaoszczedzone: { godziny: 1 },
  niedopasowani_rcp: [],
  duze_ciecia: [],
  male_ciecia: [],
  na_zmianie: [],
}

describe('RaportGodzin pay permission', () => {
  beforeEach(() => {
    authState.isAdmin = false
    authState.showPay = false
    apiMock.mockResolvedValue(RAPORT)
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('pozostawia godziny, ale ukrywa wszystkie elementy finansowe bez wyplaty.podglad', async () => {
    render(<RaportGodzin />)

    await screen.findByText('Jan Nowak')
    expect(screen.getByText('Godziny wg stanowisk')).toBeInTheDocument()
    expect(screen.queryByText('Do wypłaty (wszyscy)')).not.toBeInTheDocument()
    expect(screen.queryByText(/Koszt i godziny/)).not.toBeInTheDocument()
    expect(screen.getAllByTitle('Kelner').every((element) => !element.textContent.includes('zł'))).toBe(true)
    expect(document.body).not.toHaveTextContent('987 654')
    expect(document.body).not.toHaveTextContent('543 210')
  })

  it('pokazuje kwoty dopiero po nadaniu wyplaty.podglad', async () => {
    authState.showPay = true
    render(<RaportGodzin />)

    await screen.findByText('Jan Nowak')
    expect(screen.getByText('Do wypłaty (wszyscy)')).toBeInTheDocument()
    expect(screen.getByText('Koszt i godziny wg stanowisk')).toBeInTheDocument()
    expect(screen.getAllByTitle('Kelner').some((element) => element.textContent.includes('zł/h'))).toBe(true)
  })

  it('po cofnięciu uprawnienia usuwa stare kwoty i pobiera raport ponownie', async () => {
    authState.showPay = true
    const { rerender } = render(<RaportGodzin />)

    await screen.findByText('Jan Nowak')
    expect(screen.getByText('Do wypłaty (wszyscy)')).toBeInTheDocument()
    const callsBeforeRevocation = apiMock.mock.calls.length
    apiMock.mockResolvedValue(RAPORT_BEZ_KWOT)

    authState.showPay = false
    rerender(<RaportGodzin />)

    await waitFor(() => expect(apiMock.mock.calls.length).toBeGreaterThan(callsBeforeRevocation))
    await screen.findByText('Jan Nowak')
    expect(screen.queryByText('Do wypłaty (wszyscy)')).not.toBeInTheDocument()
    expect(screen.getByText('Godziny wg stanowisk')).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('987 654')
    expect(document.body).not.toHaveTextContent('543 210')
  })
})
