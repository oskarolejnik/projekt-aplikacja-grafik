import { createContext, useContext, useState, useCallback, useRef, useEffect, useId } from 'react'
import { Icon } from '../../lib/icons'
import { motion, AnimatePresence } from 'framer-motion'
import { SPRING } from '../../lib/motion'

// Powiadomienia (toasty) + modal potwierdzenia. Zastępują natywne alert()/confirm()
// spójnym, dostępnym UI w ciemnym motywie.
const ToastContext = createContext(null)
let idSeq = 0
const DEFAULT_TOAST_DURATION = 4200

function getToastAction(options) {
  const nestedAction = options?.action
  const label = nestedAction?.label ?? options?.actionLabel
  const onClick = nestedAction?.onClick ?? options?.onAction
  return label && typeof onClick === 'function' ? { label, onClick } : null
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [confirmState, setConfirmState] = useState(null)
  const resolver = useRef(null)
  const returnFocusRef = useRef(null)
  const confirmBtnRef = useRef(null)
  const cancelBtnRef = useRef(null)
  const confirmTitleId = useId()
  const confirmMessageId = useId()
  const toastTimers = useRef(new Map())

  const clearToastTimer = useCallback((id) => {
    const timer = toastTimers.current.get(id)
    if (timer !== undefined) {
      clearTimeout(timer)
      toastTimers.current.delete(id)
    }
  }, [])

  const dismiss = useCallback((id) => {
    clearToastTimer(id)
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [clearToastTimer])

  const toast = useCallback(
    (message, type = 'info', options = {}) => {
      const id = ++idSeq
      const action = getToastAction(options)
      const duration = Number.isFinite(options?.duration)
        ? Math.max(0, options.duration)
        : action ? 0 : DEFAULT_TOAST_DURATION
      setToasts((t) => [...t, { id, message, type, action }])
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration)
        toastTimers.current.set(id, timer)
      }
    },
    [dismiss],
  )

  useEffect(() => () => {
    toastTimers.current.forEach((timer) => clearTimeout(timer))
    toastTimers.current.clear()
  }, [])

  const runToastAction = useCallback((item) => {
    dismiss(item.id)
    item.action?.onClick()
  }, [dismiss])

  const confirm = useCallback((message, opts = {}) => {
    return new Promise((resolve) => {
      returnFocusRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
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

  // Esc zamyka modal; destrukcyjne potwierdzenie zaczyna od bezpiecznej akcji.
  useEffect(() => {
    if (!confirmState) return
    const cancel = cancelBtnRef.current
    const confirm = confirmBtnRef.current
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    ;(confirmState.danger ? cancel : confirm)?.focus()
    const onKey = (e) => {
      if (e.key === 'Escape') closeConfirm(false)
      if (e.key === 'Tab' && cancel && confirm) {
        if (e.shiftKey && document.activeElement === cancel) {
          e.preventDefault()
          confirm.focus()
        } else if (!e.shiftKey && document.activeElement === confirm) {
          e.preventDefault()
          cancel.focus()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
      const returnTarget = returnFocusRef.current
      returnFocusRef.current = null
      if (returnTarget?.isConnected) returnTarget.focus()
    }
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
        className="pointer-events-none fixed left-1/2 top-[max(1rem,calc(env(safe-area-inset-top)+0.5rem))] z-[2000] flex w-80 max-w-[calc(100vw-2rem)] -translate-x-1/2 flex-col items-center gap-2"
        aria-live="polite"
        aria-atomic="true"
      >
        {/* Sonner-like: wjazd z góry, a `layout` sprawia, że stos płynnie się
            przesuwa, gdy któryś toast znika. Wyjście szybsze niż wejście (Emil). */}
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              role={t.type === 'error' ? 'alert' : 'status'}
              initial={{ opacity: 0, y: -20, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2, ease: 'easeIn' } }}
              transition={SPRING}
              className={`pointer-events-auto flex items-start gap-3 rounded-2xl border p-3.5 text-sm shadow-soft backdrop-blur ${toastStyle[t.type] || toastStyle.info}`}
            >
              <span className="mt-0.5 shrink-0">
                <Icon name={t.type === 'error' ? 'warning' : t.type === 'success' ? 'check' : 'info'} className="h-4 w-4" />
              </span>
              <span className="min-w-0 flex-1 leading-snug">
                <span className="block">{t.message}</span>
                {t.action ? (
                  <button
                    type="button"
                    onClick={() => runToastAction(t)}
                    className="mt-2 min-h-11 rounded-xl border border-current/20 bg-white/[0.06] px-3 text-sm font-semibold transition hover:bg-white/[0.11] active:scale-[0.98]"
                  >
                    {t.action.label}
                  </button>
                ) : null}
              </span>
              <button type="button" onClick={() => dismiss(t.id)} className="-m-2 grid min-h-11 min-w-11 shrink-0 place-items-center opacity-70 transition hover:opacity-100" aria-label="Zamknij">
                <Icon name="close" className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Modal potwierdzenia (zastępuje confirm()) — Layered Entrance jak logowanie. */}
      <AnimatePresence>
        {confirmState && (
          <div className="fixed inset-0 z-[1100] grid place-items-center p-4">
            <motion.div
              aria-hidden="true"
              className="absolute inset-0 bg-black/60 backdrop-blur-md"
              onClick={() => closeConfirm(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
            />
            <motion.div
              role="alertdialog"
              aria-modal="true"
              aria-labelledby={confirmTitleId}
              aria-describedby={confirmMessageId}
              className="material relative z-10 w-full max-w-sm p-6"
              initial={{ opacity: 0, scale: 0.98, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.98, y: 10 }}
              transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
            >
              <h3 id={confirmTitleId} className="font-display text-lg font-bold text-ink">{confirmState.title}</h3>
              <p id={confirmMessageId} className="mt-2 text-sm leading-relaxed text-muted">{confirmState.message}</p>
              <div className="mt-6 flex justify-end gap-3">
                <button
                  ref={cancelBtnRef}
                  type="button"
                  onClick={() => closeConfirm(false)}
                  className="min-h-11 rounded-xl border border-line bg-white/[0.04] px-4 py-2 text-sm font-semibold text-ink transition active:scale-[0.97] hover:bg-white/[0.09]"
                >
                  {confirmState.cancelText}
                </button>
                <button
                  ref={confirmBtnRef}
                  type="button"
                  onClick={() => closeConfirm(true)}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold transition active:scale-[0.97] ${
                    confirmState.danger ? 'bg-danger text-white hover:brightness-110' : 'bg-cream text-bg hover:brightness-[1.03]'
                  }`}
                >
                  {confirmState.confirmText}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)
