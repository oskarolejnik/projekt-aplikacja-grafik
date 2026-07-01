// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { plan, apiMock, toastMock } = vi.hoisted(() => ({
  plan: {
    data: '2026-07-01', strefy: ['sala', 'ogród'],
    stoliki: [
      { id: 1, nazwa: 'S1', strefa: 'sala', pojemnosc: 4, aktywny: true, plan_x: 20, plan_y: 30, status: 'zarezerwowany',
        rezerwacje: [{ id: 9, nazwisko: 'Nowak', godz_od: '18:00', godz_do: '20:00', liczba_osob: 2, status: 'rezerwacja', kanal: 'reczna' }] },
      { id: 2, nazwa: 'S2', strefa: 'ogród', pojemnosc: 2, aktywny: true, plan_x: 60, plan_y: 50, status: 'wolny', rezerwacje: [] },
    ],
    podsumowanie: { wolne: 1, zarezerwowane: 1, nieaktywne: 0 },
  },
  apiMock: vi.fn(),
  toastMock: vi.fn(),
}))
apiMock.mockImplementation(() => Promise.resolve(plan))
vi.mock('../../lib/api', () => ({ api: apiMock }))
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))

import PlanSali from './PlanSali'

afterEach(cleanup)

describe('Plan sali (tab)', () => {
  it('renderuje stoliki, legendę i podsumowanie', async () => {
    render(<PlanSali />)
    await screen.findByText('S1')
    expect(screen.getByText('S2')).toBeInTheDocument()
    expect(screen.getByText('Wolny')).toBeInTheDocument()
    expect(screen.getByText('Potwierdzony')).toBeInTheDocument()
    // podsumowanie: 1 wolny, 1 zajęty
    expect(screen.getByText('1', { selector: 'b.text-mint' })).toBeInTheDocument()
  })

  it('klik stolika pokazuje jego rezerwacje', async () => {
    render(<PlanSali />)
    fireEvent.pointerDown(await screen.findByTitle(/S1/))
    expect(await screen.findByText(/Nowak/)).toBeInTheDocument()
    expect(screen.getByText(/18:00–20:00 · Nowak/)).toBeInTheDocument()
  })

  it('tryb edycji odsłania zapis układu', async () => {
    render(<PlanSali />)
    await screen.findByText('S1')
    fireEvent.click(screen.getByText('Edycja'))
    expect(screen.getByText('Zapisz układ')).toBeInTheDocument()
  })
})
