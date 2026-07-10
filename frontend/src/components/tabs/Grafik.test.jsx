// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock, confirmMock, reloadDictsMock, setWeekMock, toastMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  confirmMock: vi.fn(),
  reloadDictsMock: vi.fn(),
  setWeekMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../context/DataContext', () => ({
  useData: () => ({
    stanowiska: [{ id: 1, nazwa: 'Sala' }],
    pracownicy: [{
      id: 7,
      imie: 'Ania',
      nazwisko: 'Nowak',
      aktywny: true,
      dzial: 'obsluga',
      kwalifikacje: [{ id: 1 }],
    }],
    week: '2026-07-08|2026-07-14',
    biezacy: '2026-07-08|2026-07-14',
    setWeek: setWeekMock,
    reloadDicts: reloadDictsMock,
  }),
}))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ toast: toastMock, confirm: confirmMock }),
}))
vi.mock('../ui/WeekSelect', () => ({ WeekSelect: () => <div>Wybór tygodnia</div> }))
vi.mock('../ui/Hint', () => ({ Hint: ({ children }) => <span>{children}</span> }))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('../ui/Spinner', () => ({ Spinner: () => <span aria-hidden>Trwa</span> }))

import Grafik from './Grafik'

function mockGrafikApi({ publish, autoAssign, createAssignment } = {}) {
  apiMock.mockImplementation((path, method) => {
    if (path === '/grafik/kuchnia-stanowisko') return Promise.resolve({ id: 99 })
    if (path === '/zgodnosc/blokady') return Promise.resolve({})
    if (path.startsWith('/przydzialy?') && !method) return Promise.resolve([])
    if (path.startsWith('/dyspozycje?')) return Promise.resolve([])
    if (path.startsWith('/wymagania?')) return Promise.resolve([])
    if (path.startsWith('/grafik/publikacja?')) return Promise.resolve({ opublikowany: false, opublikowano_at: null })
    if (path.startsWith('/grafik/publikuj?') && method === 'POST') {
      return publish ? publish() : Promise.resolve({ opublikowano_at: '2026-07-10T12:00:00', push_wyslano: 2 })
    }
    if (path.startsWith('/auto-assign?') && method === 'POST') {
      return autoAssign ? autoAssign() : Promise.resolve({})
    }
    if (path === '/przydzialy' && method === 'POST') {
      return createAssignment ? createAssignment() : Promise.resolve({ id: 12 })
    }
    return Promise.reject(new Error(`Nieoczekiwany endpoint: ${method || 'GET'} ${path}`))
  })
}

async function renderReady() {
  render(<Grafik />)
  return screen.findByRole('button', { name: 'Dodaj zmianę: Ania Nowak, śr 08.07' })
}

beforeEach(() => {
  apiMock.mockReset()
  confirmMock.mockReset()
  reloadDictsMock.mockReset().mockResolvedValue(undefined)
  setWeekMock.mockReset()
  toastMock.mockReset()
  confirmMock.mockResolvedValue(true)
})

afterEach(cleanup)

describe('Grafik — feedback operacji', () => {
  it('pokazuje stan tylko publikowanej akcji i blokuje podwójne wysłanie', async () => {
    let resolvePublish
    mockGrafikApi({
      publish: () => new Promise((resolve) => { resolvePublish = resolve }),
    })
    await renderReady()

    fireEvent.click(screen.getByRole('button', { name: 'Udostępnij pracownikom' }))

    const pending = await screen.findByRole('button', { name: 'Udostępniam…' })
    expect(pending).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Po cichu' })).toBeDisabled()
    fireEvent.click(pending)
    expect(apiMock.mock.calls.filter(([path, method]) => path.startsWith('/grafik/publikuj?') && method === 'POST')).toHaveLength(1)

    await act(async () => resolvePublish({ opublikowano_at: '2026-07-10T12:00:00', push_wyslano: 2 }))

    expect(await screen.findByText(/Opublikowano:/)).toBeInTheDocument()
    expect(toastMock).toHaveBeenCalledWith(expect.stringContaining('Grafik udostępniony'), 'success')
  })

  it('zostawia tabelę na ekranie podczas auto-przydziału i cichego odświeżenia', async () => {
    let resolveAutoAssign
    mockGrafikApi({
      autoAssign: () => new Promise((resolve) => { resolveAutoAssign = resolve }),
    })
    const cell = await renderReady()

    fireEvent.click(screen.getByRole('button', { name: 'Auto-przydział AI' }))

    expect(await screen.findByRole('button', { name: 'Układam grafik…' })).toBeDisabled()
    expect(cell).toBeVisible()
    expect(screen.getByText(/Obecna tabela pozostaje widoczna/)).toBeInTheDocument()

    await act(async () => resolveAutoAssign({}))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Auto-przydział AI' })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'Dodaj zmianę: Ania Nowak, śr 08.07' })).toBeVisible()
  })

  it('zachowuje dane edytora i pokazuje błąd lokalnie, gdy zapis zmiany się nie uda', async () => {
    let rejectAssignment
    mockGrafikApi({
      createAssignment: () => new Promise((_, reject) => { rejectAssignment = reject }),
    })
    const cell = await renderReady()
    expect(cell).toHaveClass('min-h-11')
    fireEvent.click(cell)

    const dialog = screen.getByRole('dialog', { name: 'Ania Nowak' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Stanowisko' }), { target: { value: '1' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Rewir' }), { target: { value: 'Sala główna' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz zmianę' }))

    expect(await screen.findByRole('button', { name: 'Zapisuję zmianę…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Zamknij edycję zmiany' })).toBeDisabled()
    await act(async () => rejectAssignment(new Error('Konflikt grafiku.')))

    expect(await screen.findByRole('alert')).toHaveTextContent('Konflikt grafiku.')
    expect(dialog).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Rewir' })).toHaveValue('Sala główna')
    expect(screen.getByRole('button', { name: 'Zapisz zmianę' })).toBeEnabled()
  })
})
