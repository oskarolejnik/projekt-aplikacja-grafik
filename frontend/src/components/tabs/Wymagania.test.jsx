// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

const { apiMock, reloadDictsMock, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  reloadDictsMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/DataContext', () => ({
  useData: () => ({
    stanowiska: [{ id: 1, nazwa: 'Sala', podkategorie: [] }],
    week: '2026-07-08|2026-07-14',
    reloadDicts: reloadDictsMock,
  }),
}))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock, confirm: vi.fn() }) }))
vi.mock('../ui/WeekSelect', () => ({
  WeekSelect: ({ disabled }) => <select aria-label="Wybierz okres grafiku" disabled={disabled}><option>Bieżący tydzień</option></select>,
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../../lib/weeks', () => ({
  generujOpcjeTygodni: () => ({
    domyslny: '2026-07-01|2026-07-07',
    opcje: [
      { value: '2026-07-01|2026-07-07', label: 'Poprzedni tydzień' },
      { value: '2026-07-08|2026-07-14', label: 'Bieżący tydzień' },
    ],
  }),
}))

import Wymagania from './Wymagania'

const REQUIREMENT = {
  id: 7,
  data: '2026-07-08',
  stanowisko_id: 1,
  liczba_osob: 2,
  godz_od: '16:00:00',
  rewir: 'Sala główna',
  jest_impreza: false,
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  reloadDictsMock.mockResolvedValue(undefined)
})

describe('Wymagania', () => {
  it('zapisuje liczbę osób lokalnie bez znikania planu', async () => {
    let resolveSave
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/wymagania?')) return Promise.resolve([REQUIREMENT])
      if (path === '/wymagania' && method === 'POST') {
        return new Promise((resolve) => { resolveSave = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Wymagania />)
    const input = await screen.findByRole('spinbutton', { name: /Liczba osób: Sala/ })
    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.blur(input)

    expect(await screen.findByText('Zapisuję…')).toBeInTheDocument()
    expect(input).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Wybierz okres grafiku' })).toBeDisabled()

    await act(async () => resolveSave({ ...REQUIREMENT, liczba_osob: 3 }))

    expect(await screen.findByText('Zapisano')).toBeInTheDocument()
    expect(input).toHaveValue(3)
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/wymagania?'))).toHaveLength(1)
  })

  it('zachowuje formularz po błędzie i po retry dodaje pozycję bez pełnego przeładowania', async () => {
    let attempts = 0
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/wymagania?')) return Promise.resolve([])
      if (path === '/wymagania' && method === 'POST') {
        attempts += 1
        return attempts === 1
          ? Promise.reject(new Error('Brak połączenia.'))
          : Promise.resolve({ ...REQUIREMENT, liczba_osob: 1, rewir: 'Taras' })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Wymagania />)
    await screen.findByText(/Brak wymagań na ten tydzień/)
    fireEvent.change(screen.getByRole('combobox', { name: 'Stanowisko' }), { target: { value: '1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Rewir / strefa' }), { target: { value: 'Taras' } })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do planu' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia.')
    expect(screen.getByRole('combobox', { name: 'Stanowisko' })).toHaveValue('1')
    expect(screen.getByRole('textbox', { name: 'Rewir / strefa' })).toHaveValue('Taras')

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do planu' }))

    expect(await screen.findByText(/Dodano do planu/)).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /Liczba osób: Sala/ })).toHaveValue(1)
    expect(attempts).toBe(2)
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/wymagania?'))).toHaveLength(1)
  })

  it('usuwa wymaganie z możliwością cofnięcia', async () => {
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/wymagania?')) return Promise.resolve([REQUIREMENT])
      if (path === `/wymagania/${REQUIREMENT.id}` && method === 'DELETE') return Promise.resolve(null)
      if (path === '/wymagania' && method === 'POST') return Promise.resolve({ ...REQUIREMENT, id: 8 })
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Wymagania />)
    await screen.findByRole('spinbutton', { name: /Liczba osób: Sala/ })
    fireEvent.click(screen.getByRole('button', { name: /Usuń wymaganie: Sala/ }))

    await waitFor(() => expect(screen.queryByRole('spinbutton', { name: /Liczba osób: Sala/ })).not.toBeInTheDocument())
    const undoOptions = toastMock.mock.calls.find(([, type, options]) => type === 'info' && options?.action)?.[2]
    expect(undoOptions?.action?.label).toBe('Cofnij')

    await act(async () => undoOptions.action.onClick())

    expect(await screen.findByRole('spinbutton', { name: /Liczba osób: Sala/ })).toBeInTheDocument()
  })

  it('kopiuje tydzień jako operację drugorzędną bez zasłaniania obecnego planu', async () => {
    let resolveCopy
    apiMock.mockImplementation((path, method) => {
      if (path.startsWith('/wymagania?')) return Promise.resolve([REQUIREMENT])
      if (path === '/wymagania/kopiuj-tydzien' && method === 'POST') {
        return new Promise((resolve) => { resolveCopy = resolve })
      }
      return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
    })

    render(<Wymagania />)
    const currentPlan = await screen.findByRole('spinbutton', { name: /Liczba osób: Sala/ })
    fireEvent.change(screen.getByRole('combobox', { name: 'Na tydzień' }), { target: { value: '2026-07-08|2026-07-14' } })
    fireEvent.click(screen.getByRole('button', { name: 'Kopiuj tydzień' }))

    expect(await screen.findByRole('button', { name: 'Kopiuję tydzień…' })).toBeDisabled()
    expect(currentPlan).toBeInTheDocument()

    await act(async () => resolveCopy({ skopiowano: 4 }))

    expect(await screen.findByText('Skopiowano 4 wymagań.')).toBeInTheDocument()
    expect(apiMock.mock.calls.filter(([path]) => path.startsWith('/wymagania?'))).toHaveLength(2)
  })

  it('po błędzie wczytania pokazuje lokalny retry zamiast formularza zapisu na ślepo', async () => {
    let attempts = 0
    apiMock.mockImplementation((path) => {
      if (path.startsWith('/wymagania?')) {
        attempts += 1
        return attempts === 1 ? Promise.reject(new Error('Serwer niedostępny.')) : Promise.resolve([])
      }
      return Promise.resolve({})
    })

    render(<Wymagania />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Serwer niedostępny.')
    expect(screen.getByRole('button', { name: 'Dodaj do planu' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    expect(await screen.findByText(/Brak wymagań na ten tydzień/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dodaj do planu' })).toBeEnabled()
  })
})
