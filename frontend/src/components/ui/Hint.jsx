import { useState, useRef, useEffect, useCallback, useId } from 'react'

// Mały „?" chowający tekst objaśniający — klik odsłania dymek, ponowny klik / Esc / klik obok go chowa.
// Dymek renderowany position:fixed (pozycja z getBoundingClientRect), żeby nie był przycinany przez
// overflow kart ani stacking-context. Dostępny: aria-expanded, obsługa klawiatury, focus-visible.
export function Hint({ children, label = 'Więcej informacji', width = 260, className = '' }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const btnRef = useRef(null)
  const popRef = useRef(null)
  const tooltipId = useId()

  const umiejsc = useCallback(() => {
    const r = btnRef.current?.getBoundingClientRect()
    if (!r) return
    const left = Math.max(12, Math.min(r.left, window.innerWidth - width - 12))   // nie wychodź poza boki
    const szacH = 150                                 // szac. wysokość dymka — do decyzji dół/góra
    const podSpodem = r.bottom + 8
    // gdy pod przyciskiem brak miejsca (dolna część ekranu) → odbij dymek nad przycisk
    const top = podSpodem + szacH > window.innerHeight - 12
      ? Math.max(12, r.top - 8 - szacH)
      : podSpodem
    setPos({ top, left })
  }, [width])

  const toggle = () => { if (!open) umiejsc(); setOpen((o) => !o) }

  useEffect(() => {
    if (!open) return
    const poza = (e) => {
      if (!popRef.current?.contains(e.target) && !btnRef.current?.contains(e.target)) setOpen(false)
    }
    const klawisz = (e) => { if (e.key === 'Escape') setOpen(false) }
    const zamknij = () => setOpen(false)
    document.addEventListener('mousedown', poza)
    document.addEventListener('keydown', klawisz)
    window.addEventListener('scroll', zamknij, true)   // scroll w dowolnym kontenerze chowa dymek
    window.addEventListener('resize', zamknij)
    return () => {
      document.removeEventListener('mousedown', poza)
      document.removeEventListener('keydown', klawisz)
      window.removeEventListener('scroll', zamknij, true)
      window.removeEventListener('resize', zamknij)
    }
  }, [open])

  return (
    <span className={`relative inline-flex align-middle ${className}`}>
      <button
        type="button"
        ref={btnRef}
        onClick={toggle}
        aria-label={label}
        aria-expanded={open}
        aria-controls={open ? tooltipId : undefined}
        aria-describedby={open ? tooltipId : undefined}
        className="-m-[13px] inline-grid h-11 w-11 shrink-0 place-items-center rounded-full text-[11px] font-bold leading-none focus:outline-none focus-visible:ring-2 focus-visible:ring-mint/50"
      >
        <span className={`inline-grid h-[18px] w-[18px] place-items-center rounded-full border transition ${
          open ? 'border-mint/60 bg-mint/15 text-mint' : 'border-line bg-surface-2 text-muted hover:border-mint/40 hover:text-ink'
        }`}>
          ?
        </span>
      </button>
      {open && pos && (
        <div
          id={tooltipId}
          ref={popRef}
          role="tooltip"
          style={{ position: 'fixed', top: pos.top, left: pos.left, width, zIndex: 60 }}
          className="animate-fade-up rounded-xl border border-line bg-surface-2 p-3 text-xs leading-relaxed text-muted shadow-lg shadow-black/40"
        >
          {children}
        </div>
      )}
    </span>
  )
}
