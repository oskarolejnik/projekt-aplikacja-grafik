// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { apiMock, toastMock, confirmMock, privacyState } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  toastMock: vi.fn(),
  confirmMock: vi.fn(() => Promise.resolve(true)),
  privacyState: { callback: null },
}))

vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../../lib/reservationPrivacy', () => ({
  subscribeReservationPrivacyPurge: (callback) => {
    privacyState.callback = callback
    return () => { if (privacyState.callback === callback) privacyState.callback = null }
  },
}))
vi.mock('../ui/Toast', () => ({
  useToast: () => ({ toast: toastMock, confirm: confirmMock }),
}))

import PlanSali from './PlanSali'
import { confirmReservationLeave, hasReservationLeaveGuard } from '../../lib/reservationLeaveGuard'

const room = {
  id: 1,
  nazwa: 'Sala główna',
  aktywna: true,
  kolejnosc: 0,
  plan_id: 7,
  liczba_stolikow: 2,
  wersja_opublikowana: { id: 11, numer: 1, rewizja: 1, status: 'published' },
  szkic: null,
}
const garden = {
  id: 2,
  nazwa: 'Ogród z bardzo długą nazwą widoczną w podpowiedzi',
  aktywna: true,
  kolejnosc: 1,
  plan_id: 8,
  liczba_stolikow: 0,
  wersja_opublikowana: null,
  szkic: null,
}
const tables = [
  {
    id: 101,
    nazwa: 'S1',
    pojemnosc: 4,
    plan_x: 30,
    plan_y: 40,
    szerokosc: 12,
    wysokosc: 12,
    obrot: 0,
    aktywny_w_planie: true,
  },
  {
    id: 102,
    nazwa: 'S2',
    pojemnosc: 2,
    plan_x: 70,
    plan_y: 55,
    szerokosc: 10,
    wysokosc: 10,
    obrot: 0,
    aktywny_w_planie: true,
  },
]
const published = {
  sala: room,
  wersja: { id: 11, numer: 1, rewizja: 1, status: 'published' },
  stoliki: tables,
}
const draft = {
  sala: room,
  wersja: { id: 12, numer: 2, rewizja: 1, status: 'draft' },
  stoliki: tables,
}

const route = (path, method) => {
  if (path === '/sale-rezerwacyjne' && method === 'GET') {
    return Promise.resolve({ sale: [room, garden] })
  }
  if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') return Promise.resolve(published)
  if (path === '/sale-rezerwacyjne/2/plan' && method === 'GET') {
    return Promise.resolve({ sala: garden, wersja: null, stoliki: [] })
  }
  if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST') return Promise.resolve(draft)
  if (path === '/sale-rezerwacyjne/1/plan/szkic/stoliki' && method === 'POST') {
    return Promise.resolve({
      ...draft,
      wersja: { ...draft.wersja, rewizja: 2 },
      stoliki: [...tables, {
        id: 103,
        nazwa: 'S3',
        pojemnosc: 6,
        plan_x: 50,
        plan_y: 50,
        szerokosc: 12,
        wysokosc: 12,
        obrot: 0,
        aktywny_w_planie: true,
      }],
    })
  }
  if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
    return Promise.resolve({ ...draft, wersja: { ...draft.wersja, rewizja: 2 } })
  }
  if (path === '/sale-rezerwacyjne/1/plan/publikuj' && method === 'POST') {
    return Promise.resolve({
      ...published,
      wersja: { id: 12, numer: 2, rewizja: 2, status: 'published' },
    })
  }
  if (path.startsWith('/sale-rezerwacyjne/1/plan/szkic?') && method === 'DELETE') return Promise.resolve(null)
  return Promise.reject(new Error(`Nieoczekiwane żądanie: ${method} ${path}`))
}

describe('Plan sali R2.2', () => {
  beforeEach(() => {
    apiMock.mockReset()
    toastMock.mockReset()
    confirmMock.mockReset()
    confirmMock.mockResolvedValue(true)
    privacyState.callback = null
    apiMock.mockImplementation((path, method = 'GET') => route(path, method))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('pokazuje sale i wyłącznie opublikowany plan bez danych gościa', async () => {
    render(<PlanSali roomId={1} />)

    expect(await screen.findByRole('heading', { name: 'Sala główna' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /S1, 4 miejsca, aktywny w planie/ })).toBeInTheDocument()
    expect(screen.getByText('Opublikowany v1')).toBeInTheDocument()
    expect(screen.queryByText(/Anna Nowak|500 600 700|anna@example\.com/i)).not.toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan',
      'GET',
      null,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('tworzy szkic, obsługuje klawiaturę i zapisuje pełny snapshot z rewizją', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))

    const table = await screen.findByRole('button', { name: /S1, 4 miejsca, aktywny w planie/ })
    fireEvent.keyDown(table, { key: 'ArrowRight' })
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(31)

    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/szkic',
      'PUT',
      expect.objectContaining({
        expected_revision: 1,
        pozycje: expect.arrayContaining([
          expect.objectContaining({ stolik_id: 101, plan_x: 31, plan_y: 40 }),
        ]),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(toastMock).toHaveBeenCalledWith(
      'Szkic planu został zapisany.',
      'success',
      { scope: 'reservations' },
    )
  })

  it('nie obniża legalnej pojemności powyżej 50 przy zmianie geometrii', async () => {
    const largeTable = { ...tables[0], pojemnosc: 80, pojemnosc_min: 20 }
    const largePublished = { ...published, stoliki: [largeTable] }
    const largeDraft = { ...draft, stoliki: [largeTable] }
    apiMock.mockImplementation((path, method = 'GET', body) => {
      if (path === '/sale-rezerwacyjne' && method === 'GET') return Promise.resolve({ sale: [room] })
      if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') return Promise.resolve(largePublished)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST') return Promise.resolve(largeDraft)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        return Promise.resolve({ ...largeDraft, pozycje: body.pozycje })
      }
      return route(path, method)
    })

    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    const capacity = await screen.findByRole('spinbutton', { name: 'Miejsca przy stole' })
    expect(capacity).toHaveValue(80)
    expect(capacity).not.toHaveAttribute('max')

    fireEvent.keyDown(screen.getByRole('button', { name: /S1, 80 miejsc, aktywny w planie/ }), {
      key: 'ArrowRight',
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => {
      const payload = apiMock.mock.calls.find(([path, method]) => (
        path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
      ))?.[2]
      expect(payload.pozycje).toEqual(expect.arrayContaining([
        expect.objectContaining({ stolik_id: 101, pojemnosc: 80, pojemnosc_min: 20 }),
      ]))
    })
  })

  it('utrzymuje obrócony stół w granicach planu i zapisuje całkowitą geometrię', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))

    const canvas = screen.getByLabelText('Plan: Sala główna')
    Object.defineProperty(canvas, 'clientWidth', { configurable: true, value: 736 })
    Object.defineProperty(canvas, 'clientHeight', { configurable: true, value: 552 })

    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Szerokość stołu S1' }), {
      target: { value: '30' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Wysokość stołu S1' }), {
      target: { value: '10' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Obrót stołu S1' }), {
      target: { value: '90' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '4.6' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Pozycja Y stołu S1' }), {
      target: { value: '95' },
    })

    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(5)
    expect(screen.getByRole('spinbutton', { name: 'Pozycja Y stołu S1' })).toHaveValue(80)
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/szkic',
      'PUT',
      expect.objectContaining({
        pozycje: expect.arrayContaining([
          expect.objectContaining({
            stolik_id: 101,
            plan_x: 5,
            plan_y: 80,
            szerokosc: 30,
            wysokosc: 10,
            obrot: 90,
          }),
        ]),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
  })

  it('dodaje stół bezpośrednio do szkicu i pozostawia go nieaktywnym do publikacji', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Dodaj stół' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwa stołu' }), {
      target: { value: 'S3' },
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Liczba miejsc' }), {
      target: { value: '6' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do szkicu' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/szkic/stoliki',
      'POST',
      {
        expected_revision: 1,
        nazwa: 'S3',
        pojemnosc: 6,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByRole('button', { name: /S3, 6 miejsc, aktywny w planie/ })).toBeInTheDocument()
    expect(screen.getByText(/zacznie działać po publikacji/)).toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S3' }), {
      target: { value: '54' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/szkic',
      'PUT',
      expect.objectContaining({
        pozycje: expect.arrayContaining([
          expect.objectContaining({
            stolik_id: 103,
            plan_x: 54,
            aktywny_w_planie: true,
          }),
        ]),
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
  })

  it('przed dodaniem stołu zapisuje geometrię i zachowuje ją w nowej rewizji', async () => {
    apiMock.mockImplementation((path, method = 'GET', body) => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        return Promise.resolve({
          ...draft,
          wersja: { ...draft.wersja, rewizja: 2 },
          stoliki: tables.map((table) => ({
            ...table,
            ...(body.pozycje.find((position) => position.stolik_id === table.id) || {}),
          })),
        })
      }
      if (path === '/sale-rezerwacyjne/1/plan/szkic/stoliki' && method === 'POST') {
        return Promise.resolve({
          ...draft,
          wersja: { ...draft.wersja, rewizja: 3 },
          stoliki: [
            { ...tables[0], plan_x: 37 },
            tables[1],
            {
              id: 103,
              nazwa: body.nazwa,
              pojemnosc: body.pojemnosc,
              plan_x: 50,
              plan_y: 50,
              szerokosc: 12,
              wysokosc: 12,
              obrot: 0,
              aktywny_w_planie: true,
            },
          ],
        })
      }
      return route(path, method)
    })

    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    await screen.findByText('Szkic v2')
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '37' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj stół' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwa stołu' }), {
      target: { value: 'S3' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do szkicu' }))

    expect(await screen.findByRole('button', { name: /S3, 2 miejsca, aktywny w planie/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /S1, 4 miejsca, aktywny w planie/ }))
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(37)
    const writes = apiMock.mock.calls.filter(([path, method]) => (
      path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
    ) || (
      path === '/sale-rezerwacyjne/1/plan/szkic/stoliki' && method === 'POST'
    ))
    expect(writes.map(([path]) => path)).toEqual([
      '/sale-rezerwacyjne/1/plan/szkic',
      '/sale-rezerwacyjne/1/plan/szkic/stoliki',
    ])
    expect(writes[1][2]).toMatchObject({ expected_revision: 2, nazwa: 'S3' })
  })

  it('przed publikacją automatycznie zapisuje brudny szkic', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja Y stołu S1' }), {
      target: { value: '44' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Opublikuj' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/publikuj',
      'POST',
      { expected_revision: 2 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    expect(await screen.findByText('Opublikowany v2')).toBeInTheDocument()
  })

  it('chroni wpisany formularz stołu i nie publikuje go przez przypadek', async () => {
    confirmMock.mockResolvedValue(false)
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    await screen.findByText('Szkic v2')
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj stół' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwa stołu' }), {
      target: { value: 'S9' },
    })

    expect(hasReservationLeaveGuard()).toBe(true)
    expect(await confirmReservationLeave()).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Opublikuj' }))

    expect(confirmMock).toHaveBeenLastCalledWith(
      'Opublikować plan bez dodawania stołu wpisanego w formularzu?',
      expect.objectContaining({ title: 'Niedokończony stół' }),
    )
    expect(screen.getByRole('textbox', { name: 'Nazwa stołu' })).toHaveValue('S9')
    expect(apiMock).not.toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/publikuj',
      'POST',
      expect.anything(),
      expect.anything(),
    )
  })

  it('zachowuje lokalny szkic po wyjściu i ponownym wejściu do konfiguracji', async () => {
    const view = render(<PlanSali roomId={1} active />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '36' },
    })

    view.rerender(<PlanSali roomId={1} active={false} />)
    view.rerender(<PlanSali roomId={1} active />)

    expect(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(36)
    expect(apiMock.mock.calls.filter(([path, method]) => (
      path === '/sale-rezerwacyjne/1/plan' && method === 'GET'
    ))).toHaveLength(1)
  })

  it('po ponownym wejściu zachowuje szkic wybranej sali, gdy rodzic nie podaje już ID', async () => {
    const gardenTable = {
      ...tables[0],
      id: 201,
      nazwa: 'O1',
      plan_x: 24,
    }
    const gardenPublished = {
      sala: garden,
      wersja: { id: 21, numer: 1, rewizja: 1, status: 'published' },
      stoliki: [gardenTable],
    }
    const gardenDraft = {
      ...gardenPublished,
      wersja: { id: 22, numer: 2, rewizja: 1, status: 'draft' },
    }
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/2/plan' && method === 'GET') return Promise.resolve(gardenPublished)
      if (path === '/sale-rezerwacyjne/2/plan/szkic' && method === 'POST') return Promise.resolve(gardenDraft)
      return route(path, method)
    })

    const view = render(<PlanSali roomId={2} active />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu O1' }), {
      target: { value: '41' },
    })

    view.rerender(<PlanSali roomId={null} active={false} />)
    view.rerender(<PlanSali roomId={null} active />)

    expect(await screen.findByRole('heading', { name: garden.nazwa })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu O1' })).toHaveValue(41)
    expect(apiMock.mock.calls.filter(([path, method]) => (
      path === '/sale-rezerwacyjne/2/plan' && method === 'GET'
    ))).toHaveLength(1)
  })

  it('zachowuje ostatni poprawny plan, gdy odświeżenie tej samej sali zawiedzie', async () => {
    let planLoads = 0
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') {
        planLoads += 1
        return planLoads === 1
          ? Promise.resolve(published)
          : Promise.reject(new Error('Brak połączenia z serwerem.'))
      }
      return route(path, method)
    })

    const view = render(<PlanSali roomId={1} active />)
    expect(await screen.findByRole('button', { name: /S1, 4 miejsca/ })).toBeInTheDocument()
    view.rerender(<PlanSali roomId={1} active={false} />)
    view.rerender(<PlanSali roomId={1} active />)

    expect(await screen.findByText('Brak połączenia z serwerem.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /S1, 4 miejsca/ })).toBeInTheDocument()
  })

  it('ponawia nieudany zapis bez zastępowania lokalnej geometrii', async () => {
    let saveAttempts = 0
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        saveAttempts += 1
        if (saveAttempts === 1) return Promise.reject(new Error('Połączenie zostało przerwane.'))
      }
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '36' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    expect(await screen.findByText('Połączenie zostało przerwane.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))

    await waitFor(() => expect(saveAttempts).toBe(2))
    const retryPayload = apiMock.mock.calls.filter(([path, method]) => (
      path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
    )).at(-1)[2]
    expect(retryPayload.pozycje).toEqual(expect.arrayContaining([
      expect.objectContaining({ stolik_id: 101, plan_x: 36 }),
    ]))
  })

  it('blokuje edycję geometrii w trakcie zapisu, aby odpowiedź nie zgubiła zmian', async () => {
    let resolveSave
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        return new Promise((resolve) => { resolveSave = resolve })
      }
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    const position = await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' })
    fireEvent.change(position, { target: { value: '31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => expect(position).toBeDisabled())
    fireEvent.change(position, { target: { value: '36' } })
    expect(position).toHaveValue(31)
    resolveSave({
      ...draft,
      wersja: { ...draft.wersja, rewizja: 2 },
      stoliki: tables.map((table) => (
        table.id === 101 ? { ...table, plan_x: 31 } : table
      )),
    })

    await waitFor(() => expect(position).not.toBeDisabled())
    expect(position).toHaveValue(31)
  })

  it('zachowuje lokalne zmiany przy konflikcie rewizji i oferuje bezpieczne odświeżenie', async () => {
    const conflict = Object.assign(new Error('Konflikt planu.'), {
      status: 409,
      code: 'PLAN_REVISION_CONFLICT',
    })
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') return Promise.reject(conflict)
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '36' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    expect(await screen.findByText(/zmieniony w innej karcie/)).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(36)
    expect(screen.getByRole('button', { name: 'Pobierz nowszą wersję' })).toBeInTheDocument()
  })

  it('po zmianie listy stołów w innej karcie uzgadnia szkic zamiast zapętlać publikację', async () => {
    const snapshotError = Object.assign(new Error('Snapshot jest nieaktualny.'), {
      status: 422,
      code: 'PLAN_SNAPSHOT_INVALID',
    })
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan/publikuj' && method === 'POST') {
        return Promise.reject(snapshotError)
      }
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    await screen.findByText('Szkic v2')
    fireEvent.click(screen.getByRole('button', { name: 'Opublikuj' }))

    expect(await screen.findByText(/Lista stołów w tej sali zmieniła się/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Spróbuj ponownie' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pobierz nowszą wersję' }))
    await waitFor(() => expect(apiMock.mock.calls.filter(([path, method]) => (
      path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST'
    ))).toHaveLength(2))
  })

  it('przy konflikcie dodawania zachowuje formularz i prowadzi do uzgodnienia szkicu', async () => {
    const conflictError = Object.assign(new Error('Konflikt planu.'), {
      status: 409,
      code: 'PLAN_REVISION_CONFLICT',
    })
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic/stoliki' && method === 'POST') {
        return Promise.reject(conflictError)
      }
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    await screen.findByText('Szkic v2')
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj stół' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwa stołu' }), {
      target: { value: 'S9' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj do szkicu' }))

    expect(await screen.findByText(/Nazwa nowego stołu pozostała w formularzu/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Nazwa stołu' })).toHaveValue('S9')
    expect(screen.getByRole('button', { name: 'Pobierz nowszą wersję' })).toBeInTheDocument()
  })

  it('chroni niezapisany szkic przy przełączaniu sali', async () => {
    confirmMock.mockResolvedValue(false)
    const onRoomChange = vi.fn()
    render(<PlanSali roomId={1} onRoomChange={onRoomChange} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '38' },
    })

    fireEvent.click(screen.getByRole('button', { name: /Ogród z bardzo długą nazwą/ }))

    expect(confirmMock).toHaveBeenCalledWith(
      'Odrzucić niezapisane zmiany i wpisane dane tej sali?',
      expect.objectContaining({ title: 'Niezapisany szkic' }),
    )
    expect(onRoomChange).not.toHaveBeenCalledWith(2)
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(38)
  })

  it('nie tworzy ani nie przełącza na nową salę bez zgody na utratę szkicu', async () => {
    confirmMock.mockResolvedValue(false)
    const onRoomChange = vi.fn()
    render(<PlanSali roomId={1} onRoomChange={onRoomChange} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.change(await screen.findByRole('spinbutton', { name: 'Pozycja X stołu S1' }), {
      target: { value: '38' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Dodaj salę' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nazwa sali' }), {
      target: { value: 'Sala prywatna' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Dodaj salę' }))

    await waitFor(() => expect(confirmMock).toHaveBeenCalledWith(
      'Dodać nową salę i odrzucić niezapisane zmiany tej sali?',
      expect.objectContaining({ title: 'Niezapisany szkic' }),
    ))
    expect(apiMock).not.toHaveBeenCalledWith(
      '/sale-rezerwacyjne',
      'POST',
      expect.anything(),
      expect.anything(),
    )
    expect(onRoomChange).not.toHaveBeenCalledWith(expect.any(Number))
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(38)
  })

  it('czyści szkic i abortuje pracę po sygnale privacy purge', async () => {
    let resolveDraft
    let draftSignal
    apiMock.mockImplementation((path, method = 'GET', _body, options) => {
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST') {
        draftSignal = options.signal
        return new Promise((resolve) => { resolveDraft = resolve })
      }
      return route(path, method)
    })
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    await waitFor(() => expect(draftSignal).toBeInstanceOf(AbortSignal))

    privacyState.callback?.({ reason: 'logout' })

    expect(draftSignal.aborted).toBe(true)
    resolveDraft(draft)
    expect(screen.queryByText('Szkic v2')).not.toBeInTheDocument()
  })

  it('pokazuje opublikowane sąsiedztwo linią i równoważną listą tekstową', async () => {
    apiMock.mockImplementation((path, method = 'GET') => {
      if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') {
        return Promise.resolve({
          ...published,
          krawedzie: [{ stolik_a_id: 102, stolik_b_id: 101 }],
          kombinacje: [{
            id: 301,
            nazwa: 'S1 + S2',
            stoliki: [101, 102],
            pojemnosc_min: 5,
            pojemnosc_max: 6,
            priorytet: 0,
            kanal: 'oba',
            aktywna_w_planie: true,
          }],
        })
      }
      return route(path, method)
    })

    render(<PlanSali roomId={1} />)

    const canvas = await screen.findByLabelText('Plan: Sala główna')
    expect(canvas.querySelectorAll('line')).toHaveLength(1)
    expect(screen.getByRole('list', { name: 'S1 sąsiaduje z' })).toHaveTextContent('S2')
    expect(screen.getByRole('heading', { name: 'Zatwierdzone zestawy' })).toBeInTheDocument()
    expect(screen.getByText('5–6 osób · online i wewnętrznie')).toBeInTheDocument()
  })

  it('wyraźnie oznacza wyłączony zestaw i pozwala włączyć go w szkicu', async () => {
    const inactiveCombination = {
      id: 301,
      nazwa: 'S1 + S2',
      stoliki: [101, 102],
      pojemnosc_min: 5,
      pojemnosc_max: 6,
      priorytet: 0,
      kanal: 'oba',
      aktywna_w_planie: false,
    }
    const planWithInactive = {
      ...published,
      krawedzie: [{ stolik_a_id: 101, stolik_b_id: 102 }],
      kombinacje: [inactiveCombination],
    }
    const draftWithInactive = {
      ...draft,
      krawedzie: [{ stolik_a_id: 101, stolik_b_id: 102 }],
      kombinacje: [inactiveCombination],
    }
    apiMock.mockImplementation((path, method = 'GET', body) => {
      if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') return Promise.resolve(planWithInactive)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST') return Promise.resolve(draftWithInactive)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        return Promise.resolve({
          ...draftWithInactive,
          wersja: { ...draftWithInactive.wersja, rewizja: 2 },
          kombinacje: body.kombinacje,
        })
      }
      return route(path, method)
    })

    render(<PlanSali roomId={1} />)
    const publishedItem = (await screen.findByText('S1 + S2')).closest('li')
    expect(within(publishedItem).getByText('Wyłączony')).toBeInTheDocument()
    expect(screen.getByText(/Silnik może użyć tylko aktywnych zestawów/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Połącz stoły' }))
    const activeToggle = await screen.findByRole('checkbox', { name: 'Aktywny zestaw S1 + S2' })
    expect(activeToggle).not.toBeChecked()
    fireEvent.click(activeToggle)
    expect(activeToggle).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => {
      const payload = apiMock.mock.calls.find(([path, method]) => (
        path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
      ))?.[2]
      expect(payload.kombinacje).toEqual([
        expect.objectContaining({ stoliki: [101, 102], aktywna_w_planie: true }),
      ])
    })
  })

  it('łączy dwa stoły, cofa i ponawia zmianę oraz zapisuje pełny snapshot', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Połącz stoły' }))

    fireEvent.click(screen.getByRole('button', { name: /^S1,/ }))
    fireEvent.click(screen.getByRole('button', { name: /^S2,/ }))

    const canvas = screen.getByLabelText('Plan: Sala główna')
    expect(canvas.querySelectorAll('line')).toHaveLength(1)
    expect(screen.getAllByText('Połączono S1 i S2.')).not.toHaveLength(0)
    expect(hasReservationLeaveGuard()).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Cofnij' }))
    expect(canvas.querySelectorAll('line')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))
    expect(canvas.querySelectorAll('line')).toHaveLength(1)
    fireEvent.keyDown(canvas, { key: 'z', ctrlKey: true })
    expect(canvas.querySelectorAll('line')).toHaveLength(0)
    fireEvent.keyDown(canvas, { key: 'z', ctrlKey: true, shiftKey: true })
    expect(canvas.querySelectorAll('line')).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź' }))
    expect(screen.getByText('Brak zatwierdzonego zestawu lub pojedynczego stołu dla 18 osób.')).toBeInTheDocument()
    expect(screen.getByText(/nie uwzględnia dostępności w konkretnym terminie/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/sale-rezerwacyjne/1/plan/szkic',
      'PUT',
      expect.objectContaining({
        krawedzie: [{ stolik_a_id: 101, stolik_b_id: 102 }],
        kombinacje: [],
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
  })

  it('traktuje całe przeciągnięcie jako jeden krok historii', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    const canvas = await screen.findByLabelText('Plan: Sala główna')
    vi.spyOn(canvas, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 1000,
      height: 750,
      right: 1000,
      bottom: 750,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    const table = screen.getByRole('button', { name: /^S1,/ })

    fireEvent.pointerDown(table, { pointerId: 7, clientX: 300, clientY: 300 })
    fireEvent.pointerMove(canvas, { pointerId: 7, clientX: 360, clientY: 330 })
    fireEvent.pointerMove(canvas, { pointerId: 7, clientX: 400, clientY: 345 })
    fireEvent.pointerUp(canvas, { pointerId: 7, clientX: 400, clientY: 345 })

    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(40)
    fireEvent.click(screen.getByRole('button', { name: 'Cofnij' }))
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(30)
    expect(screen.getByRole('button', { name: 'Cofnij' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))
    expect(screen.getByRole('spinbutton', { name: 'Pozycja X stołu S1' })).toHaveValue(40)
  })

  it('zatwierdza spójny zestaw dla 18 osób oraz edytuje zakres, kanał i priorytet', async () => {
    const tablesFor18 = [
      { ...tables[0], pojemnosc: 4 },
      { ...tables[1], pojemnosc: 6 },
      {
        ...tables[1],
        id: 103,
        nazwa: 'S3',
        pojemnosc: 8,
        plan_x: 85,
        plan_y: 55,
      },
    ]
    const publishedFor18 = { ...published, stoliki: tablesFor18, krawedzie: [], kombinacje: [] }
    const draftFor18 = {
      ...draft,
      stoliki: tablesFor18,
      krawedzie: [],
      kombinacje: [],
    }
    apiMock.mockImplementation((path, method = 'GET', body) => {
      if (path === '/sale-rezerwacyjne/1/plan' && method === 'GET') return Promise.resolve(publishedFor18)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'POST') return Promise.resolve(draftFor18)
      if (path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT') {
        return Promise.resolve({
          ...draftFor18,
          wersja: { ...draftFor18.wersja, rewizja: 2 },
          stoliki: body.pozycje.map((position) => ({
            ...tablesFor18.find((table) => table.id === position.stolik_id),
            ...position,
          })),
          krawedzie: body.krawedzie,
          kombinacje: body.kombinacje,
        })
      }
      return route(path, method)
    })

    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Połącz stoły' }))
    fireEvent.click(screen.getByRole('button', { name: /^S1,/ }))
    fireEvent.click(screen.getByRole('button', { name: /^S2,/ }))
    fireEvent.click(screen.getByRole('button', { name: /^S2,/ }))
    fireEvent.click(screen.getByRole('button', { name: /^S3,/ }))

    const proposal = screen.getByText('S1 + S2 + S3').closest('li')
    fireEvent.click(within(proposal).getByRole('button', { name: 'Zatwierdź' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Od osób' }), { target: { value: '10' } })
    const maximum = screen.getByRole('spinbutton', { name: 'Do osób' })
    fireEvent.change(maximum, { target: { value: '99' } })
    expect(maximum).toHaveValue(18)
    fireEvent.change(screen.getByRole('combobox', { name: 'Kanał' }), { target: { value: 'wewnetrzna' } })
    const seatingPriority = screen.getByRole('spinbutton', { name: 'Priorytet obsadzania' })
    expect(seatingPriority).toHaveValue(0)
    fireEvent.change(seatingPriority, { target: { value: '-3' } })
    expect(screen.getByText(/Niższa liczba zwiększa szansę wyboru przy podobnym dopasowaniu/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Sprawdź' }))

    expect(screen.getByText('Ten układ obsłuży 18 osób: S1 + S2 + S3.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))
    await waitFor(() => {
      const payload = apiMock.mock.calls.find(([path, method]) => (
        path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
      ))?.[2]
      expect(payload.krawedzie).toEqual([
        { stolik_a_id: 101, stolik_b_id: 102 },
        { stolik_a_id: 102, stolik_b_id: 103 },
      ])
      expect(payload.kombinacje).toEqual(expect.arrayContaining([
        expect.objectContaining({
          nazwa: 'S1 + S2 + S3',
          stoliki: [101, 102, 103],
          pojemnosc_min: 10,
          pojemnosc_max: 18,
          kanal: 'wewnetrzna',
          priorytet: -3,
        }),
      ]))
    })
  })

  it('edytuje snapshotowane właściwości stołu wyłącznie przez pełny zapis szkicu', async () => {
    render(<PlanSali roomId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Edytuj jako szkic' }))

    fireEvent.change(await screen.findByRole('textbox', { name: 'Nazwa na planie' }), { target: { value: 'S1 przy oknie' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Miejsca przy stole' }), { target: { value: '6' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Minimum osób' }), { target: { value: '3' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Kształt' }), { target: { value: 'okragly' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Priorytet' }), { target: { value: '-2' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'Sekcja' }), { target: { value: 'A' } })
    const features = screen.getByRole('textbox', { name: 'Cechy' })
    fireEvent.change(features, { target: { value: 'okno,' } })
    expect(features).toHaveValue('okno,')
    fireEvent.change(features, { target: { value: 'okno, loża' } })
    fireEvent.blur(features)

    expect(apiMock.mock.calls.some(([path, method]) => path.startsWith('/stoliki') && method !== 'GET')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Zapisz szkic' }))

    await waitFor(() => {
      const payload = apiMock.mock.calls.find(([path, method]) => (
        path === '/sale-rezerwacyjne/1/plan/szkic' && method === 'PUT'
      ))?.[2]
      expect(payload.pozycje).toEqual(expect.arrayContaining([
        expect.objectContaining({
          stolik_id: 101,
          nazwa: 'S1 przy oknie',
          pojemnosc: 6,
          pojemnosc_min: 3,
          ksztalt: 'okragly',
          priorytet: -2,
          sekcja: 'A',
          cechy: ['okno', 'loża'],
        }),
      ]))
    })
  })
})
