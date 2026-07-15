// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import ReservationAllocationSummary from './ReservationAllocationSummary'

const allocation = {
  state: 'preview',
  visibility: 'exact',
  room: { id: 1, name: 'Sala Główna' },
  tables: [
    { id: 11, name: 'S1', capacity: 6 },
    { id: 12, name: 'S2', capacity: 6 },
    { id: 13, name: 'S3', capacity: 6 },
  ],
  capacity: 18,
  visit_end: '20:30',
  reasons: [
    { code: 'CAPACITY_FIT', message: '18 miejsc dla 18 osób' },
    { code: 'TABLES_ADJACENT', message: 'Stoły sąsiadują' },
    { code: 'ROOM_STRICT_PRIORITY', message: 'Sala Główna jest obsadzana jako pierwsza' },
  ],
  alternatives: [
    {
      id: 'later',
      kind: 'time',
      date: '2026-08-22',
      time: '18:30',
      allocation: {
        room: { id: 2, name: 'Ogród' },
        tables: [{ id: 21, name: 'O1', capacity: 18 }],
      },
    },
    { id: 'waitlist', kind: 'waitlist' },
  ],
}

describe('ReservationAllocationSummary', () => {
  afterEach(() => cleanup())

  it('pokazuje pełną rekomendację, powody i ostrzeżenie, że podgląd nie jest blokadą', () => {
    const { container } = render(<ReservationAllocationSummary allocation={allocation} />)

    expect(screen.getByText('Proponowany przydział')).toBeInTheDocument()
    expect(screen.getByText('Sala Główna · S1 + S2 + S3')).toBeInTheDocument()
    expect(screen.getByText('18 miejsc · do 20:30')).toBeInTheDocument()
    expect(screen.getByText('18 miejsc dla 18 osób')).toBeInTheDocument()
    expect(screen.getByText('Stoły sąsiadują')).toBeInTheDocument()
    expect(screen.getByText('Sala Główna jest obsadzana jako pierwsza')).toBeInTheDocument()
    expect(screen.getByText('Podgląd nie blokuje stołów; przydział potwierdzi się przy zapisie.')).toBeInTheDocument()
    expect(container.querySelector('[aria-live="polite"]')).toHaveTextContent('Sala Główna · S1 + S2 + S3')
    expect(container.firstChild).toHaveClass('border-y', 'min-w-0')
  })

  it('rozwija alternatywy kontrolką 44 px i przekazuje wybrany wariant', () => {
    const onSelectAlternative = vi.fn()
    render(
      <ReservationAllocationSummary
        allocation={allocation}
        onSelectAlternative={onSelectAlternative}
      />,
    )

    const disclosure = screen.getByRole('button', { name: /Pokaż 2 alternatywy/ })
    expect(disclosure).toHaveClass('min-h-11')
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(disclosure)

    expect(screen.getByRole('button', { name: /Ukryj alternatywy/ })).toHaveAttribute('aria-expanded', 'true')
    const list = screen.getByRole('list', { name: 'Alternatywne przydziały' })
    const later = within(list).getByRole('button', { name: '2026-08-22 · 18:30 · Ogród · O1' })
    expect(later).toHaveClass('min-h-11', 'w-full')
    fireEvent.click(later)

    expect(onSelectAlternative).toHaveBeenCalledWith(allocation.alternatives[0], 0)
    expect(within(list).getByRole('button', { name: 'Lista oczekujących' })).toBeInTheDocument()
  })

  it('w trybie availability_only nie ujawnia nazw sal, stołów ani powodów wyboru', () => {
    render(
      <ReservationAllocationSummary
        allocation={{
          ...allocation,
          visibility: 'availability_only',
          alternatives: [{
            kind: 'room',
            allocation: {
              room: { name: 'Sekretna sala' },
              tables: [{ name: 'Ukryty stolik' }],
            },
          }],
        }}
      />,
    )

    expect(screen.getByText('Miejsce jest dostępne')).toBeInTheDocument()
    expect(screen.getByText('Dokładny stolik przydzieli obsługa')).toBeInTheDocument()
    expect(screen.queryByText(/Sala Główna/)).not.toBeInTheDocument()
    expect(screen.queryByText(/S1/)).not.toBeInTheDocument()
    expect(screen.queryByText(/18 miejsc dla/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Pokaż 1 alternatywę' }))
    expect(screen.getByText('Inne dostępne miejsce')).toBeInTheDocument()
    expect(screen.queryByText(/Sekretna sala/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Ukryty stolik/)).not.toBeInTheDocument()
  })

  it('oznacza ręczny przydział i bezpiecznie zawija długie nazwy', () => {
    const longTable = 'Stół-bardzo-długi-bez-spacji-który-musi-zostać-zawinięty-na-telefonie'
    render(
      <ReservationAllocationSummary
        allocation={{
          state: 'manual_locked',
          visibility: 'exact',
          room: { name: 'Sala bankietowa z wyjątkowo długą nazwą operacyjną' },
          tables: [{ name: longTable }],
          capacity: { seats: 12 },
        }}
      />,
    )

    expect(screen.getByText('Przypisano ręcznie')).toBeInTheDocument()
    expect(screen.getByText('Automat nie zmieni tego przydziału.')).toBeInTheDocument()
    const primary = screen.getByText(new RegExp(longTable))
    expect(primary).toHaveClass('break-words', 'min-w-0')
    expect(screen.queryByText(/Podgląd nie blokuje/)).not.toBeInTheDocument()
  })

  it('odróżnia zapisany przydział od niewiążącego podglądu', () => {
    render(
      <ReservationAllocationSummary
        allocation={{ ...allocation, state: 'assigned', alternatives: [] }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Przydzielono' })).toBeInTheDocument()
    expect(screen.getByText('Sala Główna · S1 + S2 + S3')).toBeInTheDocument()
    expect(screen.queryByText(/Podgląd nie blokuje/)).not.toBeInTheDocument()
  })

  it('przyjmuje alternatywy także jako osobny element kontraktu', () => {
    render(
      <ReservationAllocationSummary
        allocation={{ ...allocation, alternatives: [] }}
        alternatives={[{ kind: 'time', time: '19:15' }]}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Pokaż 1 alternatywę' }))
    expect(screen.getByText('19:15')).toBeInTheDocument()
  })
})
