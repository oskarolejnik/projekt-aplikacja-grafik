import { useId, useLayoutEffect, useRef } from 'react'
import { Icon } from '../../lib/icons'

export function DialogFrame({
  title,
  closeLabel,
  onClose,
  maxWidth = 'max-w-md',
  initialFocusRef,
  restoreFocusRef,
  children,
}) {
  const titleId = useId()
  const panelRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useLayoutEffect(() => {
    const previousFocus = document.activeElement
    const panel = panelRef.current
    const focusableSelector = [
      'button:not([disabled])',
      'input:not([disabled])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(',')
    const initial = initialFocusRef?.current || panel?.querySelector(focusableSelector)
    initial?.focus()

    const onKeyDown = (event) => {
      // Modal potwierdzenia ToastProvider ma pierwszeństwo przed formularzem pod spodem.
      if (document.querySelector('[role="alertdialog"]')) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current?.()
        return
      }
      if (event.key !== 'Tab' || !panel) return
      const focusable = [...panel.querySelectorAll(focusableSelector)]
        .filter((node) => node.getClientRects().length > 0)
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      requestAnimationFrame(() => {
        const restoreTarget = restoreFocusRef?.current || previousFocus
        if (!restoreTarget?.isConnected) return

        // Przy atomowym przejściu dialog → dialog cleanup starego ekranu
        // wykonuje się po ustawieniu fokusu w nowym. Nie wolno wtedy przenieść
        // fokusu do kontrolki pod aktywnym overlayem. Nadal pozwalamy zagnieżdżonemu
        // dialogowi wrócić do kontrolki wewnątrz modala, który pozostał otwarty.
        const openModals = document.querySelectorAll([
          '[role="dialog"][aria-modal="true"]',
          '[role="alertdialog"][aria-modal="true"]',
        ].join(','))
        const topModal = openModals[openModals.length - 1]
        if (topModal && !topModal.contains(restoreTarget)) return

        restoreTarget.focus()
      })
    }
  }, [initialFocusRef, restoreFocusRef])

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`material max-h-[90dvh] w-full ${maxWidth} overflow-y-auto p-5 shadow-soft sm:p-6`}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h3 id={titleId} className="font-display text-lg font-semibold text-ink">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="-m-2 grid min-h-11 min-w-11 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-white/[0.06] hover:text-ink"
            aria-label={closeLabel}
          >
            <Icon name="close" className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
