// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { setWeekMock } = vi.hoisted(() => ({ setWeekMock: vi.fn() }))

vi.mock('../../context/DataContext', () => ({
  useData: () => ({
    week: '2026-07-08|2026-07-14',
    setWeek: setWeekMock,
    weeks: [
      { value: '2026-07-08|2026-07-14', label: 'Bieżący tydzień' },
      { value: '2026-07-15|2026-07-21', label: 'Przyszły tydzień' },
    ],
  }),
}))
vi.mock('../../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import { Hint } from './Hint'
import { PillSwitch } from './PillSwitch'
import { WeekSelect } from './WeekSelect'

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('wspólne kontrolki', () => {
  it('PillSwitch komunikuje aktywną opcję i ma wygodne cele dotykowe', () => {
    const onChange = vi.fn()
    render(
      <PillSwitch
        label="Dostępność"
        value="tak"
        onChange={onChange}
        options={[{ value: 'tak', label: 'Tak' }, { value: 'nie', label: 'Nie' }]}
      />,
    )

    expect(screen.getByRole('group', { name: 'Dostępność' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tak' })).toHaveAttribute('aria-pressed', 'true')
    const nie = screen.getByRole('button', { name: 'Nie' })
    expect(nie).toHaveAttribute('aria-pressed', 'false')
    expect(nie.className).toContain('min-h-11')
    fireEvent.click(nie)
    expect(onChange).toHaveBeenCalledWith('nie')
  })

  it('WeekSelect dopasowuje się do szerokości i zmienia okres', () => {
    render(<WeekSelect />)
    const select = screen.getByRole('combobox', { name: 'Wybierz okres grafiku' })
    expect(select.parentElement.className).toContain('min-w-0')
    expect(select.className).toContain('sm:min-w-[280px]')
    fireEvent.change(select, { target: { value: '2026-07-15|2026-07-21' } })
    expect(setWeekMock).toHaveBeenCalledWith('2026-07-15|2026-07-21')
  })

  it('WeekSelect pozwala widokowi zatrzymać zmianę okresu z niezapisanym formularzem', async () => {
    const beforeChange = vi.fn().mockResolvedValue(false)
    render(<WeekSelect beforeChange={beforeChange} />)
    const select = screen.getByRole('combobox', { name: 'Wybierz okres grafiku' })

    fireEvent.change(select, { target: { value: '2026-07-15|2026-07-21' } })

    await waitFor(() => expect(beforeChange).toHaveBeenCalledWith(
      '2026-07-15|2026-07-21',
      '2026-07-08|2026-07-14',
    ))
    expect(setWeekMock).not.toHaveBeenCalled()
    expect(select).not.toBeDisabled()
  })

  it('WeekSelect może zablokować zmianę okresu podczas trwającej operacji', () => {
    render(<WeekSelect disabled />)

    expect(screen.getByRole('combobox', { name: 'Wybierz okres grafiku' })).toBeDisabled()
  })

  it('Hint ma 44-pikselowy cel i łączy przycisk z podpowiedzią', () => {
    render(<Hint>Treść pomocy</Hint>)
    const button = screen.getByRole('button', { name: 'Więcej informacji' })
    expect(button.className).toContain('h-11')
    expect(button.className).toContain('w-11')

    fireEvent.click(button)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('Treść pomocy')
    expect(button).toHaveAttribute('aria-describedby', tooltip.id)

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
