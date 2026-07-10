// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { refreshMock, enableMock, toastMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
  enableMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../lib/push', () => ({
  pushWspierany: () => true,
  odswiezSubskrypcje: refreshMock,
  wlaczPowiadomienia: enableMock,
}))
vi.mock('../lib/platforma', () => ({ jestNatywna: () => false }))
vi.mock('../lib/pushNative', () => ({ zarejestrujPushNatywny: vi.fn() }))
vi.mock('./ui/Toast', () => ({ useToast: () => ({ toast: toastMock }) }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))

import { PushButton } from './PushButton'

describe('PushButton', () => {
  beforeEach(() => {
    refreshMock.mockReset().mockResolvedValue(false)
    enableMock.mockReset()
    toastMock.mockReset()
  })

  afterEach(cleanup)

  it('ma cel 44 px, lokalny pending i blokuje podwójne żądanie', async () => {
    let resolveEnable
    enableMock.mockImplementation(() => new Promise((resolve) => { resolveEnable = resolve }))
    render(<PushButton />)

    const ready = screen.getByRole('button', { name: 'Włącz powiadomienia' })
    expect(ready).toHaveClass('min-h-11', 'min-w-11')

    fireEvent.click(ready)
    fireEvent.click(ready)

    const pending = screen.getByRole('button', { name: 'Włączam powiadomienia' })
    expect(pending).toBeDisabled()
    expect(pending).toHaveAttribute('aria-busy', 'true')
    expect(enableMock).toHaveBeenCalledTimes(1)

    await act(async () => resolveEnable())

    await waitFor(() => expect(screen.getByRole('button', { name: 'Powiadomienia włączone' })).toHaveAttribute('aria-pressed', 'true'))
    expect(toastMock).toHaveBeenCalledWith('Powiadomienia włączone.', 'success')
  })
})
