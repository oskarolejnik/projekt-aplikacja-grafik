// @vitest-environment jsdom
import React, { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { LazyErrorBoundary } from './LazyFallback'

function BrokenView() {
  throw new Error('chunk unavailable')
}

describe('LazyErrorBoundary', () => {
  afterEach(cleanup)

  it('pozwala ponowić ładowanie widoku bez opuszczania aplikacji', async () => {
    const consoleMock = vi.spyOn(console, 'error').mockImplementation(() => {})
    const preventError = (event) => event.preventDefault()
    window.addEventListener('error', preventError)

    function RetryHarness() {
      const [failed, setFailed] = useState(true)
      return (
        <LazyErrorBoundary onRetry={() => setFailed(false)}>
          {failed ? <BrokenView /> : <div>Widok gotowy</div>}
        </LazyErrorBoundary>
      )
    }

    try {
      render(<RetryHarness />)

      expect(screen.getByRole('alert')).toHaveTextContent('Nie udało się wczytać widoku')
      fireEvent.click(screen.getByRole('button', { name: 'Spróbuj ponownie' }))
      expect(await screen.findByText('Widok gotowy')).toBeInTheDocument()
    } finally {
      window.removeEventListener('error', preventError)
      consoleMock.mockRestore()
    }
  })

  it('umożliwia pełne odświeżenie po awarii powierzchni aplikacji', () => {
    const consoleMock = vi.spyOn(console, 'error').mockImplementation(() => {})
    const reload = vi.fn()
    const preventError = (event) => event.preventDefault()
    window.addEventListener('error', preventError)

    try {
      render(
        <LazyErrorBoundary fullPage reload={reload}>
          <BrokenView />
        </LazyErrorBoundary>,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Odśwież aplikację' }))
      expect(reload).toHaveBeenCalledOnce()
    } finally {
      window.removeEventListener('error', preventError)
      consoleMock.mockRestore()
    }
  })
})
