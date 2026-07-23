// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'
import CrmGovernanceTools from './CrmGovernanceTools'
import { purgeReservationPrivacy } from '../../lib/reservationPrivacy'

const { apiMock, downloadMock } = vi.hoisted(() => ({
  apiMock: vi.fn(),
  downloadMock: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  api: apiMock,
  pobierzPlikPost: downloadMock,
}))

const QUALITY = {
  podsumowanie: {
    mozliwe_duplikaty: 1,
    bez_kontaktu: 2,
    zgody_bez_dowodu: 3,
    profile_osierocone: 0,
  },
  kandydaci: [{
    id: 71,
    source_ref: 101,
    target_ref: 202,
    powod: 'Wspólny adres e-mail',
    source: {
      nazwisko: 'Anna Kowalska',
      telefon: '600 700 800',
      wizyt: 3,
    },
    target: {
      nazwisko: 'Anna K.',
      email: 'anna@example.test',
      wizyt: 2,
    },
    source_hash: 'source-secret-hash',
    target_hash: 'target-secret-hash',
  }],
  aktywne_scalenia: [{
    id: 44,
    source: { nazwisko: 'Jan Nowak' },
    target: { nazwisko: 'Jan N.' },
  }],
}

const PREVIEW = {
  expected_version: 5,
  source: {
    nazwisko: 'Anna Kowalska',
    telefon: '600 700 800',
    wizyt: 3,
  },
  target: {
    nazwisko: 'Anna K.',
    email: 'anna@example.test',
    wizyt: 2,
  },
  konflikty: [{
    pole: 'Nazwisko',
    source: 'Anna Kowalska',
    target: 'Anna K.',
  }],
  ostrzezenia: ['Sprawdź, czy kontakt nie jest współdzielony przez rodzinę.'],
}

function deferred() {
  let resolve
  const promise = new Promise((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

beforeEach(() => {
  apiMock.mockReset()
  downloadMock.mockReset()
  downloadMock.mockResolvedValue(undefined)
  apiMock.mockImplementation((path) => {
    if (path === '/crm/jakosc') return Promise.resolve(QUALITY)
    if (path === '/crm/scalenia/podglad') return Promise.resolve(PREVIEW)
    if (path === '/crm/scalenia') return Promise.resolve({ id: 45 })
    if (path.endsWith('/cofnij')) return Promise.resolve({ status: 'undone' })
    return Promise.resolve({})
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('CrmGovernanceTools R7.3', () => {
  it('ładuje jakość dopiero po rozwinięciu i scala po jawnym porównaniu z idempotencją', async () => {
    const onChanged = vi.fn()
    render(<CrmGovernanceTools searchBody={{ q: 'Anna', vip: true }} onChanged={onChanged} />)

    expect(apiMock).not.toHaveBeenCalled()
    const toggle = screen.getByRole('button', { name: /pokaż narzędzia/i })
    fireEvent.click(toggle)

    expect(await screen.findByText('Możliwe duplikaty')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Anna Kowalska')).toBeInTheDocument()
    expect(screen.queryByText('source-secret-hash')).not.toBeInTheDocument()
    expect(screen.queryByText('target-secret-hash')).not.toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith('/crm/jakosc', 'GET', null, {
      signal: expect.any(AbortSignal),
    })

    const previewTrigger = screen.getByRole('button', { name: 'Porównaj' })
    fireEvent.click(previewTrigger)

    expect(await screen.findByRole('dialog', { name: 'Porównaj profile' })).toBeInTheDocument()
    expect(apiMock).toHaveBeenCalledWith(
      '/crm/scalenia/podglad',
      'POST',
      { source_ref: 101, target_ref: 202 },
      { signal: expect.any(AbortSignal) },
    )
    expect(screen.getByText('Sprawdź, czy kontakt nie jest współdzielony przez rodzinę.')).toBeInTheDocument()

    const mergeButton = screen.getByRole('button', { name: 'Scal profile' })
    expect(mergeButton).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', {
      name: /potwierdzam, że oba profile dotyczą tej samej osoby/i,
    }))
    fireEvent.click(mergeButton)

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/crm/scalenia',
      'POST',
      {
        source_ref: 101,
        target_ref: 202,
        reason_code: 'duplicate_confirmed',
        expected_version: 5,
      },
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        headers: {
          'Idempotency-Key': expect.stringMatching(/^crm-merge-/),
        },
      }),
    ))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog', { name: 'Porównaj profile' })).not.toBeInTheDocument()
    await waitFor(() => expect(previewTrigger).toHaveFocus())
  })

  it('cofa aktywne scalenie po ostrzeżeniu i zachowuje lokalny stan sukcesu', async () => {
    const onChanged = vi.fn()
    render(<CrmGovernanceTools onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))
    await screen.findByText('Jan Nowak')

    const undoTrigger = screen.getByRole('button', { name: 'Cofnij' })
    fireEvent.click(undoTrigger)

    expect(screen.getByRole('dialog', { name: 'Cofnąć scalenie?' })).toHaveTextContent(
      'Żadne dane nie zostaną usunięte',
    )
    expect(screen.getByRole('button', { name: 'Zostaw scalenie' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cofnij scalenie' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/crm/scalenia/44/cofnij',
      'POST',
      {},
      expect.objectContaining({
        headers: {
          'Idempotency-Key': expect.stringMatching(/^crm-merge-undo-/),
        },
      }),
    ))
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('Scalenie zostało cofnięte. Oba profile znów są rozdzielone.')).toBeInTheDocument()
    await waitFor(() => expect(undoTrigger).toHaveFocus())
  })

  it('eksportuje dokładnie bieżące filtry i pokazuje błąd z retry', async () => {
    const searchBody = {
      q: 'Kowalska',
      vip: true,
      ryzyko: null,
      min_wizyt: 3,
      sort: 'wizyty_desc',
      offset: 0,
      limit: 25,
    }
    downloadMock
      .mockRejectedValueOnce(new Error('Eksport chwilowo niedostępny.'))
      .mockResolvedValueOnce(undefined)

    render(<CrmGovernanceTools searchBody={searchBody} />)
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))
    await screen.findByText('Eksport bieżącego wyniku')

    fireEvent.click(screen.getByRole('button', { name: 'Pobierz CSV' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Eksport chwilowo niedostępny.')
    expect(downloadMock).toHaveBeenLastCalledWith(
      '/crm/eksport',
      searchBody,
      expect.stringMatching(/^goscie_crm_\d{4}-\d{2}-\d{2}\.csv$/),
      { signal: expect.any(AbortSignal) },
    )

    fireEvent.click(screen.getByRole('button', { name: 'Ponów eksport' }))
    await waitFor(() => expect(downloadMock).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Eksport bieżącego wyniku został pobrany.')).toBeInTheDocument()
  })

  it('nie pozwala spóźnionemu podglądowi zmienić pary wybranej do scalenia', async () => {
    const firstPreview = deferred()
    const secondPreview = deferred()
    const quality = {
      ...QUALITY,
      kandydaci: [
        QUALITY.kandydaci[0],
        {
          ...QUALITY.kandydaci[0],
          id: 72,
          source_ref: 303,
          target_ref: 404,
          source: { nazwisko: 'Ewa Nowak', wizyt: 2 },
          target: { nazwisko: 'Ewa N.', wizyt: 3 },
        },
      ],
    }
    let previewCall = 0
    apiMock.mockImplementation((path) => {
      if (path === '/crm/jakosc') return Promise.resolve(quality)
      if (path === '/crm/scalenia/podglad') {
        previewCall += 1
        return previewCall === 1 ? firstPreview.promise : secondPreview.promise
      }
      if (path === '/crm/scalenia') return Promise.resolve({ id: 73 })
      return Promise.resolve({})
    })

    render(<CrmGovernanceTools />)
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))
    const previewButtons = await screen.findAllByRole('button', { name: 'Porównaj' })

    fireEvent.click(previewButtons[0])
    const staleSignal = apiMock.mock.calls.find(
      ([path]) => path === '/crm/scalenia/podglad',
    )[3].signal
    fireEvent.click(screen.getByRole('button', { name: 'Zamknij porównanie' }))
    expect(staleSignal.aborted).toBe(true)

    fireEvent.click(previewButtons[1])
    await act(async () => {
      secondPreview.resolve({
        ...PREVIEW,
        source: { nazwisko: 'Ewa Nowak' },
        target: { nazwisko: 'Ewa N.' },
        konflikty: [{
          pole: 'Nazwisko',
          source: 'Ewa Nowak',
          target: 'Ewa N.',
        }],
      })
    })
    const dialog = await screen.findByRole('dialog', { name: 'Porównaj profile' })
    expect(within(dialog).getAllByText('Ewa Nowak')).not.toHaveLength(0)

    await act(async () => {
      firstPreview.resolve(PREVIEW)
      await Promise.resolve()
    })
    expect(within(dialog).queryByText('Anna Kowalska')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', {
      name: /potwierdzam, że oba profile dotyczą tej samej osoby/i,
    }))
    fireEvent.click(screen.getByRole('button', { name: 'Scal profile' }))

    await waitFor(() => expect(apiMock).toHaveBeenCalledWith(
      '/crm/scalenia',
      'POST',
      expect.objectContaining({ source_ref: 303, target_ref: 404 }),
      expect.anything(),
    ))
  })

  it('blokuje eksport, dopóki widoczny wynik nie odpowiada filtrom', async () => {
    const { rerender } = render(
      <CrmGovernanceTools searchBody={{ q: 'Anna' }} exportReady={false} />,
    )
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))

    const exportButton = await screen.findByRole('button', { name: 'Pobierz CSV' })
    expect(exportButton).toBeDisabled()
    fireEvent.click(exportButton)
    expect(downloadMock).not.toHaveBeenCalled()

    rerender(<CrmGovernanceTools searchBody={{ q: 'Ewa' }} exportReady />)
    expect(screen.getByRole('button', { name: 'Pobierz CSV' })).toBeEnabled()
  })

  it('dla prawa tylko do eksportu nie odpytuje narzędzi jakości', async () => {
    render(<CrmGovernanceTools canManage={false} canExport />)

    expect(screen.getByText('Eksport danych gości')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))

    expect(await screen.findByRole('button', { name: 'Pobierz CSV' })).toBeInTheDocument()
    expect(screen.queryByText('Do sprawdzenia')).not.toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalledWith(
      '/crm/jakosc',
      'GET',
      null,
      expect.anything(),
    )
  })

  it('pokazuje błąd jakości z retry, a privacy purge abortuje i usuwa PII z widoku', async () => {
    const pending = deferred()
    apiMock.mockReset()
    apiMock
      .mockRejectedValueOnce(new Error('Brak połączenia z CRM.'))
      .mockReturnValueOnce(pending.promise)

    render(<CrmGovernanceTools />)
    fireEvent.click(screen.getByRole('button', { name: /pokaż narzędzia/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Brak połączenia z CRM.')
    fireEvent.click(screen.getByRole('button', { name: 'Ponów' }))
    await waitFor(() => expect(apiMock).toHaveBeenCalledTimes(2))
    const signal = apiMock.mock.calls[1][3].signal

    act(() => {
      purgeReservationPrivacy({ reason: 'logout', broadcast: false })
    })

    expect(signal.aborted).toBe(true)
    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()
    expect(screen.queryByText('Jakość danych i eksport')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /pokaż narzędzia/i })).toHaveAttribute('aria-expanded', 'false')

    await act(async () => {
      pending.resolve(QUALITY)
      await Promise.resolve()
    })
    expect(screen.queryByText('Anna Kowalska')).not.toBeInTheDocument()
  })
})
