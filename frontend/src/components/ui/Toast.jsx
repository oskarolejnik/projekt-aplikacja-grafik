import { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react'
import { Icon } from '../../lib/icons'

// Powiadomienia (toasty) + modal potwierdzenia. Zastępują natywne alert()/confirm()
// spójnym, dostępnym UI w ciemnym motywie.
const ToastContext = createContext(null)
let idSeq = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [confirmState, setConfirmState] = useState(null)
  const resolver = useRef(null)
  const confirmBtnRef = useRef(null)

  const dismiss = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const toast = useCallback(
    (message, type = 'info') => {
      const id = ++idSeq
      setToasts((t) => [...t, { id, message, type }])
      setTimeout(() => dismiss(id), 4200)
    },
    [dismiss],
  )

  const confirm = useCallback((message, opts = {}) => {
    return new Promise((resolve) => {
      resolver.current = resolve
      setConfirmState({
        message,
        title: opts.title || 'Na pewno?',
        confirmText: opts.confirmText || 'Potwierdź',
        cancelText: opts.cancelText || 'Anuluj',
        danger: opts.danger !== false,
      })
    })
  }, [])

  const closeConfirm = useCallback((result) => {
    setConfirmState(null)
    if (resolver.current) {
      resolver.current(result)
      resolver.current = null
    }
  }, [])

  // Esc zamyka modal, a po otwarciu fokus trafia na przycisk potwierdzenia.
  useEffect(() => {
    if (!confirmState) return
    confirmBtnRef.current?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeConfirm(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [confirmState, closeConfirm])

  const toastStyle = {
    error: 'border-danger/40 bg-danger/15 text-red-50',
    success: 'border-success/40 bg-success/15 text-emerald-50',
    info: 'border-line bg-surface-2/95 text-ink',
  }

  return (
    <ToastContext.Provider value={{ toast, confirm }}>
      {children}

      {/* Stos toastów (prawy górny róg) */}
      <div
        className="pointer-events-none fixed right-[max(1rem,env(safe-area-inset-right))] top-[max(1rem,calc(env(safe-area-inset-top)+0.5rem))] z-[1000] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`animate-fade-in pointer-events-auto flex items-start gap-3 rounded-xl border p-3.5 text-sm shadow-soft backdrop-blur ${toastStyle[t.type] || toastStyle.info}`}
          >
            <span className="mt-0.5 shrink-0">
              <Icon name={t.type === 'error' ? 'warning' : t.type === 'success' ? 'check' : 'info'} className="h-4 w-4" />
            </span>
            <span className="flex-1 leading-snug">{t.message}</span>
            <button onClick={() => dismiss(t.id)} className="shrink-0 opacity-70 transition hover:opacity-100" aria-label="Zamknij">
              <Icon name="close" className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Modal potwierdzenia (zastępuje confirm()) */}
      {confirmState && (
        <div className="fixed inset-0 z-[1100] grid place-items-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => closeConfirm(false)} />
          <div role="alertdialog" aria-modal="true" className="card animate-fade-in relative z-10 w-full max-w-sm p-6">
            <h3 className="font-display text-lg font-bold text-ink">{confirmState.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{confirmState.message}</p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => closeConfirm(false)}
                className="rounded-xl border border-line bg-white/[0.04] px-4 py-2 text-sm font-semibold text-ink transition hover:bg-white/[0.09]"
              >
                {confirmState.cancelText}
              </button>
              <button
                ref={confirmBtnRef}
                onClick={() => closeConfirm(true)}
                className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                  confirmState.danger ? 'bg-danger text-white hover:brightness-110' : 'bg-cream text-bg hover:brightness-[1.03]'
                }`}
              >
                {confirmState.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
