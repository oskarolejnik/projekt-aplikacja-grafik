import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { useToast } from '../ui/Toast'

// Plan sali — wizualne rozmieszczenie stolików (pozycje w % kontenera) + status na wybrany
// dzień z rezerwacji. Podgląd = kolory statusu + szczegóły; Edycja = przeciąganie i zapis układu.
const dzisISO = () => new Date().toISOString().slice(0, 10)
const clamp = (v) => Math.max(0, Math.min(100, v))

const STATUS = {
  wolny:         { bg: 'bg-mint/10 border-mint/50 text-mint',   dot: 'bg-mint',      label: 'Wolny' },
  zarezerwowany: { bg: 'bg-lemon/10 border-lemon/50 text-lemon', dot: 'bg-lemon',    label: 'Zarezerwowany' },
  potwierdzony:  { bg: 'bg-coral/10 border-coral/50 text-coral', dot: 'bg-coral',    label: 'Potwierdzony' },
  nieaktywny:    { bg: 'bg-white/[0.02] border-line text-muted/60', dot: 'bg-white/20', label: 'Nieaktywny' },
}

// Auto-siatka dla stolików bez zapisanej pozycji.
function autoPoz(i, n) {
  const cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.7)))
  const rows = Math.max(1, Math.ceil(n / cols))
  return { x: Math.round(((i % cols) + 0.5) / cols * 100), y: Math.round((Math.floor(i / cols) + 0.5) / rows * 100) }
}

export default function PlanSali() {
  const { toast } = useToast()
  const [data, setData] = useState(dzisISO())
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tryb, setTryb] = useState('podglad')   // podglad | edycja
  const [poz, setPoz] = useState({})            // id -> {x,y} (%), lokalny stan edycji
  const [dragId, setDragId] = useState(null)
  const [brudne, setBrudne] = useState(false)
  const [wybrany, setWybrany] = useState(null)
  const [busy, setBusy] = useState(false)
  const box = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const p = await api(`/plan-sali?data=${data}`)
      setPlan(p)
      const n = p.stoliki.length
      const next = {}
      p.stoliki.forEach((s, i) => {
        next[s.id] = (s.plan_x != null && s.plan_y != null) ? { x: s.plan_x, y: s.plan_y } : autoPoz(i, n)
      })
      setPoz(next); setBrudne(false)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [data, toast])
  useEffect(() => { load() }, [load])

  const onMove = (e) => {
    if (dragId == null || !box.current) return
    const r = box.current.getBoundingClientRect()
    setPoz((p) => ({ ...p, [dragId]: { x: clamp(Math.round((e.clientX - r.left) / r.width * 100)), y: clamp(Math.round((e.clientY - r.top) / r.height * 100)) } }))
    setBrudne(true)
  }
  const onDown = (e, id) => {
    if (tryb !== 'edycja') { setWybrany((w) => (w === id ? null : id)); return }
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* brak capture → drag i tak działa nad elementem */ }
    setDragId(id)
  }

  // Przełączenie trybu. Wyjście z Edycji z niezapisanym układem gubi „Zapisz" (chowa się w Podglądzie),
  // więc pytamy o potwierdzenie i — po zgodzie — odrzucamy zmiany, przeładowując zapisany układ.
  const zmienTryb = (k) => {
    if (k === tryb) return
    if (tryb === 'edycja' && brudne) {
      if (!window.confirm('Masz niezapisane zmiany układu sali. Wyjść z edycji i je odrzucić?')) return
      load()   // przywróć pozycje z ostatnio zapisanego planu (odrzuca przeciągnięcia)
    }
    setTryb(k); setWybrany(null)
  }

  const zapisz = async () => {
    setBusy(true)
    try {
      const pozycje = plan.stoliki.map((s) => ({ id: s.id, plan_x: poz[s.id].x, plan_y: poz[s.id].y }))
      await api('/plan-sali/pozycje', 'PUT', pozycje)
      toast('Układ sali zapisany.', 'success'); setBrudne(false)
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const stoliki = plan?.stoliki || []
  const wybranyStolik = useMemo(() => stoliki.find((s) => s.id === wybrany) || null, [stoliki, wybrany])

  return (
    <Card className="p-6 sm:p-8">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="Plan sali" subtitle="Rozmieszczenie stolików i status na wybrany dzień. W trybie edycji przeciągnij stoliki." />
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <input type="date" value={data} onChange={(e) => setData(e.target.value)} disabled={tryb === 'edycja'}
                 className="rounded-lg border border-line bg-surface px-3 py-1.5 text-ink outline-none focus:border-mint disabled:opacity-50" />
          <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5">
            {[['podglad', 'Podgląd'], ['edycja', 'Edycja']].map(([k, l]) => (
              <button key={k} onClick={() => zmienTryb(k)}
                className={`rounded-md px-3 py-1 text-sm font-semibold transition ${tryb === k ? 'bg-accent-gradient text-bg' : 'text-muted hover:text-ink'}`}>{l}</button>
            ))}
          </div>
          {tryb === 'edycja' && (
            <button onClick={zapisz} disabled={busy || !brudne}
              className="rounded-lg bg-cream px-3 py-1.5 text-sm font-bold text-bg transition hover:brightness-[1.03] disabled:opacity-50">
              {busy ? 'Zapisuję…' : 'Zapisz układ'}
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="grid place-items-center py-24"><Spinner className="h-6 w-6 text-muted" /></div>
      ) : stoliki.length === 0 ? (
        <div className="rounded-xl border border-line bg-surface-2 p-10 text-center text-sm text-muted">
          Brak stolików. Dodaj je w zakładce „Rezerwacje stolików", potem ułóż tutaj plan sali.
        </div>
      ) : (
        <>
          {/* Podsumowanie + legenda */}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-4 text-xs">
              {Object.entries(STATUS).map(([k, v]) => (
                <span key={k} className="inline-flex items-center gap-1.5 text-muted">
                  <span className={`h-2.5 w-2.5 rounded-full ${v.dot}`} /> {v.label}
                </span>
              ))}
            </div>
            <div className="text-xs text-muted">
              Wolne: <b className="text-mint">{plan.podsumowanie.wolne}</b> · Rezerwacje: <b className="text-coral">{plan.podsumowanie.zarezerwowane}</b>
              {plan.podsumowanie.zajete_live > 0 && <> · <span className="inline-flex items-center gap-1"><span className="h-2 w-2 animate-pulse rounded-full bg-coral" />Live: <b className="text-coral">{plan.podsumowanie.zajete_live}</b></span></>}
              {plan.podsumowanie.nieaktywne > 0 && <> · Nieaktywne: {plan.podsumowanie.nieaktywne}</>}
            </div>
          </div>

          {/* Plansza */}
          <div
            ref={box}
            className={`relative w-full overflow-hidden rounded-2xl border border-line bg-surface-grad ${tryb === 'edycja' ? 'cursor-grab' : ''}`}
            style={{ aspectRatio: '16 / 9', backgroundImage: 'radial-gradient(rgba(255,255,255,0.05) 1px, transparent 1px)', backgroundSize: '28px 28px' }}
          >
            {stoliki.map((s) => {
              const p = poz[s.id] || { x: 50, y: 50 }
              const st = STATUS[s.status] || STATUS.wolny
              const rozmiar = 46 + Math.min(10, s.pojemnosc || 2) * 3
              return (
                <button
                  key={s.id}
                  onPointerDown={(e) => onDown(e, s.id)}
                  onPointerMove={tryb === 'edycja' ? onMove : undefined}
                  onPointerUp={() => setDragId(null)}
                  className={`absolute grid place-items-center rounded-2xl border text-center transition-[border-color,background-color] ${st.bg} ${tryb === 'edycja' ? 'cursor-grab active:cursor-grabbing' : 'cursor-pointer'} ${wybrany === s.id ? 'ring-2 ring-mint ring-offset-2 ring-offset-bg' : ''} ${dragId === s.id ? 'z-20 scale-105 shadow-glow' : 'z-10'}`}
                  style={{ left: `${p.x}%`, top: `${p.y}%`, width: rozmiar, height: rozmiar, transform: 'translate(-50%,-50%)', touchAction: 'none' }}
                  title={`${s.nazwa} · ${s.pojemnosc} os. · ${st.label}`}
                >
                  <span className="font-display text-xs font-bold leading-none text-ink">{s.nazwa}</span>
                  <span className="mt-0.5 flex items-center gap-0.5 text-[10px] leading-none text-muted">
                    <Icon name="users" className="h-2.5 w-2.5" />{s.pojemnosc}
                  </span>
                  {s.rezerwacje.length > 0 && (
                    <span className={`absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[9px] font-bold text-bg ${st.dot}`}>{s.rezerwacje.length}</span>
                  )}
                  {s.live?.zajete && (
                    <span className="absolute -left-1 -top-1 flex h-3 w-3" title={`Zajęty na żywo (POS): ${s.live.otwarte} otwartych rachunków`}>
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-coral opacity-70" />
                      <span className="relative inline-flex h-3 w-3 rounded-full bg-coral" />
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Szczegóły wybranego stolika (podgląd) */}
          {tryb === 'podglad' && wybranyStolik && (
            <div className="mt-4 rounded-xl border border-line bg-surface-2 p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="font-display text-sm font-bold text-ink">
                  {wybranyStolik.nazwa}
                  <span className="ml-2 text-xs font-normal text-muted">{wybranyStolik.strefa || 'sala'} · {wybranyStolik.pojemnosc} os.</span>
                </div>
                <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STATUS[wybranyStolik.status]?.bg}`}>{STATUS[wybranyStolik.status]?.label}</span>
              </div>
              {wybranyStolik.live?.zajete && (
                <div className="mb-2 flex items-center gap-2 rounded-lg bg-coral/[0.08] px-3 py-1.5 text-xs text-coral">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-coral" />
                  Na żywo (POS): {wybranyStolik.live.otwarte} otwartych rachunków
                </div>
              )}
              {wybranyStolik.rezerwacje.length === 0 ? (
                <p className="text-sm text-muted">Brak rezerwacji na {plan.data}.</p>
              ) : (
                <ul className="space-y-1.5">
                  {wybranyStolik.rezerwacje.map((r) => (
                    <li key={r.id} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink">{r.godz_od || '—'}{r.godz_do ? `–${r.godz_do}` : ''} · {r.nazwisko}</span>
                      <span className="flex items-center gap-2 text-xs text-muted">
                        <span className="inline-flex items-center gap-0.5"><Icon name="users" className="h-3 w-3" />{r.liczba_osob || '?'}</span>
                        <span className={`rounded-full px-2 py-0.5 ${r.status === 'potwierdzona' ? 'bg-coral/15 text-coral' : 'bg-lemon/15 text-lemon'}`}>{r.status}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {tryb === 'podglad' && !wybranyStolik && (
            <p className="mt-3 text-center text-xs text-muted">Kliknij stolik, aby zobaczyć jego rezerwacje.</p>
          )}
        </>
      )}
    </Card>
  )
}
