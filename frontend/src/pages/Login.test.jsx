// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

const { loginMock, toastMock } = vi.hoisted(() => ({
  loginMock: vi.fn(),
  toastMock: vi.fn(),
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ login: loginMock, register: vi.fn() }),
}))
vi.mock('../context/BrandingContext', () => ({
  useBranding: () => ({ nazwa_lokalu: 'Lokalo Test' }),
}))
vi.mock('../components/ui/Toast', () => ({
  useToast: () => ({ toast: toastMock }),
}))
vi.mock('../components/Logo', () => ({ Logo: () => <span aria-hidden /> }))
vi.mock('../lib/icons', () => ({ Icon: () => <span aria-hidden /> }))
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }) => <div {...props}>{children}</div>,
  },
}))

import Login from './Login'

describe('Login', () => {
  beforeEach(() => {
    loginMock.mockReset()
    toastMock.mockReset()
    window.localStorage.clear()
  })

  afterEach(cleanup)

  it('pozwala zalogować starsze konto identyfikatorem bez znaku @', async () => {
    let resolveLogin
    loginMock.mockImplementation(() => new Promise((resolve) => { resolveLogin = resolve }))
    render(<Login />)

    const identyfikator = screen.getByLabelText('E-mail lub login')
    expect(identyfikator).toHaveAttribute('type', 'text')
    expect(identyfikator).toHaveAttribute('autocomplete', 'username')

    fireEvent.change(identyfikator, { target: { value: 'qaemployee' } })
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'LokaloQA1!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Zaloguj się' }))

    expect(await screen.findByRole('button', { name: 'Loguję…' })).toBeDisabled()
    expect(loginMock).toHaveBeenCalledWith('qaemployee', 'LokaloQA1!', true)

    resolveLogin({ rola: 'employee' })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Zaloguj się' })).not.toBeDisabled())
    expect(toastMock).not.toHaveBeenCalled()
  })
})
