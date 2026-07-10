// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, confirmMock, toastMock, pobierzPlikMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  toastMock: vi.fn(),
  pobierzPlikMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock, pobierzPlik: pobierzPlikMock }))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ toast: toastMock, confirm: confirmMock }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import Ustawienia from './Ustawienia'

const CONFIG = {
  nazwa_lokalu: 'Lokalo Test',
  logo_url: null,
  kolor_primary: '#9DC4B1',
  typ_lokalu: null,
  poczatek_tygodnia: 0,
  grafik_cykl: 'tydzien',
  modul_rezerwacje: true,
  modul_imprezy: true,
  modul_rozliczenia: true,
  modul_pos: true,
  modul_sprzatanie: true,
  rezerwacje_online: false,
  rezerwacje_auto_potwierdzenie: false,
  impreza_osoby_na_obsluge: 15,
  impreza_wyprzedzenie_min: 120,
  impreza_najwczesniej: '10:00',
  impreza_sale_min2: '',
  obsada_rachunki_na_osobe: 20,
  obsada_min: 1,
  praca_min_odpoczynek_h: 11,
  praca_max_dni_tydzien: 6,
  praca_max_dni_miesiac: 22,
  impreza_osobne_rozliczenie: false,
  rozliczenia_tryb_kelnera: 'indywidualnie',
  rozliczenia_nazwy_kas: [],
  rozliczenia_nazwy_terminali: [],
  sale: [],
  sprzatanie_sale_codziennie: [],
  sprzatanie_sala_niedziela: '',
  imprezy_mapa_sal: {},
  zeszyt_kolumny: [],
  imprezy_excel_mapa: {},
  faktura_nip: '',
  faktura_nazwa: '',
  faktura_adres_l1: '',
  faktura_adres_l2: '',
}

const SUB = {
  stan: 'aktywna',
  status: 'aktywna',
  tier: 'pro',
  data_do: null,
  cena_brutto: 199,
  saldo_kredytu: 0,
  trial_dni: null,
  dostepne_moduly: [
    'modul_rezerwacje',
    'modul_imprezy',
    'modul_rozliczenia',
    'modul_pos',
    'modul_sprzatanie',
  ],
  moduly_wg_planu: {},
}

const installApi = ({ failAux = false, oferty = [] } = {}) => {
  apiMock.mockImplementation((path, method) => {
    if (path === '/lokal/config' && method === 'PUT') return Promise.resolve({ ok: true })
    if (path === '/lokal/config') return Promise.resolve({ ...CONFIG })
    if (path === '/integracje/status') {
      return failAux ? Promise.reject(new Error('Integracje offline')) : Promise.resolve({ integracje: [] })
    }
    if (path === '/subskrypcja') {
      return failAux ? Promise.reject(new Error('Plan offline')) : Promise.resolve({ ...SUB })
    }
    if (path === '/oferty-menu' && !method) return Promise.resolve(oferty)
    if (path === '/faktury') return Promise.resolve({ tryb_ksef: 'stub', faktury: [] })
    if (path.startsWith('/oferty-menu/')) return Promise.resolve({})
    return Promise.resolve({})
  })
}

describe('Ustawienia', () => {
  beforeEach(() => {
    apiMock.mockReset()
    confirmMock.mockResolvedValue(true)
    installApi()
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('dzieli monolit na cztery dostępne obszary i pokazuje tylko wybrany', async () => {
    render(<Ustawienia />)

    await screen.findByRole('heading', { name: /Marka \(white-label\)/ })
    expect(screen.getByRole('group', { name: 'Kategoria ustawień' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Rozliczenie dnia/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Operacje' }))
    expect(screen.getByRole('heading', { name: /Rozliczenie dnia/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /Marka \(white-label\)/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Goście' }))
    expect(screen.getByRole('heading', { name: /Rezerwacje online/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Plan' }))
    expect(screen.getByRole('heading', { name: /Subskrypcja \/ licencja/ })).toBeInTheDocument()
  })

  it('nie blokuje konfiguracji, gdy pomocnicze integracje i plan są niedostępne', async () => {
    installApi({ failAux: true })
    render(<Ustawienia />)

    await screen.findByRole('heading', { name: /Marka \(white-label\)/ })
    fireEvent.click(screen.getByRole('button', { name: 'Plan' }))
    expect(screen.getByText(/Nie udało się sprawdzić planu/)).toBeInTheDocument()
    expect(screen.getByText(/Nie udało się pobrać statusu integracji/)).toBeInTheDocument()
  })

  it('ponawia tylko subskrypcję i zachowuje niezapisaną konfigurację', async () => {
    let subAttempts = 0
    apiMock.mockImplementation((path, method) => {
      if (path === '/lokal/config') return Promise.resolve({ ...CONFIG })
      if (path === '/integracje/status') return Promise.resolve({ integracje: [] })
      if (path === '/subskrypcja') {
        subAttempts += 1
        return subAttempts === 1
          ? Promise.reject(new Error('Plan offline'))
          : Promise.resolve({ ...SUB })
      }
      if (path === '/oferty-menu' && !method) return Promise.resolve([])
      if (path === '/faktury') return Promise.resolve({ tryb_ksef: 'stub', faktury: [] })
      return Promise.resolve({})
    })
    render(<Ustawienia />)

    const nazwa = await screen.findByLabelText('Nazwa lokalu')
    fireEvent.change(nazwa, { target: { value: 'Niezapisana nazwa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Spróbuj ponownie' }))

    await waitFor(() => expect(subAttempts).toBe(2))
    expect(screen.queryByText(/Nie udało się sprawdzić planu/)).not.toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([path, method]) => path === '/lokal/config' && !method)).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Lokal' }))
    expect(screen.getByLabelText('Nazwa lokalu')).toHaveValue('Niezapisana nazwa')
  })

  it('zachowuje edycję między obszarami i wysyła ją przy zapisie', async () => {
    render(<Ustawienia />)

    const nazwa = await screen.findByLabelText('Nazwa lokalu')
    fireEvent.change(nazwa, { target: { value: 'Nowa nazwa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Operacje' }))
    fireEvent.click(screen.getByRole('button', { name: 'Lokal' }))
    expect(screen.getByLabelText('Nazwa lokalu')).toHaveValue('Nowa nazwa')

    fireEvent.click(screen.getByRole('button', { name: 'Zapisz ustawienia' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith('/lokal/config', 'PUT', expect.objectContaining({
      nazwa_lokalu: 'Nowa nazwa',
    })))
  })

  it('ma nazwane przełączniki 44 px i potwierdza usunięcie oferty', async () => {
    const oferta = { id: 7, nazwa: 'Menu Klasyczne', opis: '', cena_od_osoby: 190, aktywna: true }
    installApi({ oferty: [oferta] })
    render(<Ustawienia />)

    await screen.findByRole('heading', { name: /Marka \(white-label\)/ })
    fireEvent.click(screen.getByRole('button', { name: 'Goście' }))
    const toggle = screen.getByRole('switch', { name: 'Włącz rezerwacje online' })
    expect(toggle.className).toContain('min-h-11')
    expect(toggle.className).toContain('min-w-11')

    confirmMock.mockResolvedValueOnce(false)
    fireEvent.click(await screen.findByRole('button', { name: 'Usuń ofertę Menu Klasyczne' }))
    await waitFor(() => expect(confirmMock).toHaveBeenCalled())
    expect(apiMock.mock.calls.some(([path, method]) => path === '/oferty-menu/7' && method === 'DELETE')).toBe(false)
  })
})
