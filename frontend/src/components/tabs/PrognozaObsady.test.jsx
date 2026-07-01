// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from 'vitest'
import { render, screen, cleanup, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// Mock warstwy API + toastów — testujemy prezentację prognozy obsady.
// vi.hoisted: fabryki vi.mock są hoistowane, więc dane muszą powstać w tym samym hoistowanym bloku.
const { dane, apiMock, toastMock } = vi.hoisted(() => ({
  dane: {
    okres_dni: 90,
    probek: 90,
    srednia_dzienna: 50.7,
    trend_28d_proc: 4.2,
    parametry_obsady: { rachunki_na_osobe: 20, min: 1 },
    per_dzien_tygodnia: [],
    projekcja_7dni: [
      { data: '2026-07-03', nazwa: 'Piątek', prognoza: 75.0, sugerowana_obsada: 4 },
      { data: '2026-07-04', nazwa: 'Sobota', prognoza: 90.2, sugerowana_obsada: 5 },
      { data: '2026-07-06', nazwa: 'Poniedziałek', prognoza: 0, sugerowana_obsada: 1 },
    ],
  },
  apiMock: vi.fn(),
  toastMock: vi.fn(),
}))
apiMock.mockImplementation(() => Promise.resolve(dane))
vi.mock('../../lib/api', () => ({ api: apiMock }))
// Stabilna referencja toast — inaczej useCallback([toast]) pętli load() w kółko.
vi.mock('../ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))

import PrognozaObsady from './PrognozaObsady'

afterEach(cleanup)

describe('Prognoza obsady (tab)', () => {
  it('pobiera prognozę i pokazuje sugerowaną obsadę per dzień', async () => {
    render(<PrognozaObsady />)
    const sobKom = await screen.findByText('Sobota')
    const wiersz = (nazwa) => within(screen.getByText(nazwa).closest('tr'))
    // Sobota: prognoza 90.2 → 5 osób; Poniedziałek 0 → min 1.
    expect(sobKom.closest('tr').textContent).toContain('90.2')
    expect(wiersz('Sobota').getByText('5')).toBeInTheDocument()
    expect(wiersz('Poniedziałek').getByText('1')).toBeInTheDocument()  // pusty ruch → minimum
    expect(apiMock).toHaveBeenCalledWith(expect.stringContaining('/prognoza-ruchu'))
  })

  it('pokazuje KPI parametrów obsady i średni ruch', async () => {
    const { container } = render(<PrognozaObsady />)
    await screen.findByText('Sobota')
    const t = container.textContent
    expect(t).toContain('50.7')       // średni ruch
    expect(t).toContain('+4.2%')      // trend
    expect(t).toContain('rachunków/osobę')
  })
})
