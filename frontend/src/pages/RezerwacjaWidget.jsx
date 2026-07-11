import { useState, useCallback, useRef } from 'react'
import { api, nowyKluczIdempotencji } from '../lib/api'
import { useBranding } from '../context/BrandingContext'
import { useToast } from '../components/ui/Toast'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { Logo } from '../components/Logo'

// Publiczny widget rezerwacji online (gość, bez logowania). Korzysta z /api/online/*.
const dzisISO = () => new Date().toISOString().slice(0, 10)
const fld = 'w-full rounded-xl border border-line bg-surface px-4 py-3 text-sm text-ink outline-none focus:border-mint'

export default function RezerwacjaWidget() {
  const { nazwa_lokalu } = useBranding()
  const { toast } = useToast()
  const [krok, setKrok] = useState('wybor')          // wybor | formularz | sukces
  const [data, setData] = useState(dzisISO())
  const [osoby, setOsoby] = useState(2)
  const [sloty, setSloty] = useState(null)           // null = nie szukano, [] = brak
  const [loading, setLoading] = useState(false)
  const [niedostepne, setNiedostepne] = useState(false)
  const [slot, setSlot] = useState(null)
  const [form, setForm] = useState({ nazwisko: '', telefon: '', email: '', notatka: '' })
  const [busy, setBusy] = useState(false)
  const [wynik, setWynik] = useState(null)           // { token, rezerwacja }
  const probaZapisuRef = useRef(null)

  const szukaj = useCallback(async () => {
    setLoading(true); setSloty(null); setNiedostepne(false)
    try {
      const r = await api(`/online/dostepnosc?data=${data}&osoby=${osoby}`)
      setSloty(r.sloty || [])
    } catch (e) {
      if (/niedost|nie.*dost|404/i.test(e.message)) setNiedostepne(true)
      else toast(e.message, 'error')
      setSloty([])
    } finally { setLoading(false) }
  }, [data, osoby, toast])

  const rezerwuj = async () => {
    if (busy || !slot) return
    if (!form.nazwisko.trim()) { toast('Podaj imię i nazwisko.', 'error'); return }
    const body = {
      data, godz_od: slot, liczba_osob: Number(osoby), nazwisko: form.nazwisko.trim(),
      telefon: form.telefon || null, email: form.email || null, notatka: form.notatka || null,
    }
    const fingerprint = JSON.stringify(body)
    if (probaZapisuRef.current?.fingerprint !== fingerprint) {
      probaZapisuRef.current = {
        fingerprint,
        key: nowyKluczIdempotencji('online-reservation'),
      }
    }
    setBusy(true)
    try {
      const r = await api('/online/rezerwacja', 'POST', body, {
        headers: { 'Idempotency-Key': probaZapisuRef.current.key },
      })
      probaZapisuRef.current = null
      setWynik(r); setKrok('sukces')
    } catch (e) {
      if (e.code === 'IDEMPOTENCY_KEY_REUSED') probaZapisuRef.current = null
      toast(e.message, 'error')
    } finally { setBusy(false) }
  }

  const odwolaj = async () => {
    try {
      await api(`/online/rezerwacja/${wynik.token}/odwolaj`, 'POST')
      toast('Rezerwacja odwołana.', 'info')
      setWynik((w) => ({ ...w, rezerwacja: { ...w.rezerwacja, status: 'odwolana' } }))
    } catch (e) { toast(e.message, 'error') }
  }

  const dataLabel = new Date(data).toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="relative min-h-dvh bg-bg px-4 py-10">
      <div aria-hidden className="scena-swiatlo pointer-events-none fixed inset-0" />
      <div className="relative z-10 mx-auto w-full max-w-lg">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-9" variant="gradient" />
          <div>
            <h1 className="font-display text-xl font-bold text-ink">{nazwa_lokalu}</h1>
            <p className="text-xs text-muted">Rezerwacja stolika online</p>
          </div>
        </div>

        <div className="card p-6 sm:p-8">
          {/* KROK 1 — wybór dnia i osób + sloty */}
          {krok === 'wybor' && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs font-semibold text-muted">Data
                  <input type="date" min={dzisISO()} value={data} onChange={(e) => { setData(e.target.value); setSloty(null) }} className={fld} /></label>
                <label className="text-xs font-semibold text-muted">Liczba osób
                  <input type="number" min="1" value={osoby} onChange={(e) => { setOsoby(e.target.value); setSloty(null) }} className={fld} /></label>
              </div>
              <button onClick={szukaj} disabled={loading}
                className="mt-4 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 disabled:opacity-60">
                {loading ? 'Szukam…' : 'Sprawdź dostępność'}
              </button>

              {loading && <div className="grid place-items-center py-8"><Spinner className="h-6 w-6 text-muted" /></div>}

              {niedostepne && (
                <div className="mt-5 rounded-xl border border-line bg-surface-2 p-4 text-center text-sm text-muted">
                  Rezerwacje online są obecnie niedostępne. Prosimy o kontakt telefoniczny.
                </div>
              )}

              {sloty && !niedostepne && (
                sloty.some((s) => s.wolne > 0) ? (
                  <div className="mt-5">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted capitalize">{dataLabel} — wolne godziny</div>
                    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                      {sloty.map((s) => (
                        <button key={s.godz_od} disabled={s.wolne === 0}
                          onClick={() => { setSlot(s.godz_od); setKrok('formularz') }}
                          className={`rounded-xl border px-2 py-2.5 text-sm font-semibold transition ${s.wolne > 0 ? 'border-line text-ink hover:border-mint hover:bg-white/[0.04]' : 'border-line/50 text-muted/40'}`}>
                          {s.godz_od}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="mt-5 rounded-xl border border-line bg-surface-2 p-4 text-center text-sm text-muted">
                    Brak wolnych stolików w wybranym dniu. Spróbuj innego terminu.
                  </div>
                )
              )}
            </>
          )}

          {/* KROK 2 — formularz */}
          {krok === 'formularz' && (
            <>
              <button onClick={() => setKrok('wybor')} className="mb-3 inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-ink">‹ wstecz</button>
              <div className="mb-4 rounded-xl border border-mint/30 bg-mint/5 px-4 py-3 text-sm text-ink">
                <span className="capitalize">{dataLabel}</span>, godz. <b>{slot}</b> · {osoby} os.
              </div>
              <div className="space-y-3">
                <label className="block text-xs font-semibold text-muted">Imię i nazwisko
                  <input value={form.nazwisko} onChange={(e) => setForm((s) => ({ ...s, nazwisko: e.target.value }))} className={fld} placeholder="Jan Kowalski" /></label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs font-semibold text-muted">Telefon
                    <input value={form.telefon} onChange={(e) => setForm((s) => ({ ...s, telefon: e.target.value }))} className={fld} /></label>
                  <label className="text-xs font-semibold text-muted">E-mail
                    <input value={form.email} onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))} className={fld} /></label>
                </div>
                <label className="block text-xs font-semibold text-muted">Uwagi (opcjonalnie)
                  <textarea rows={2} value={form.notatka} onChange={(e) => setForm((s) => ({ ...s, notatka: e.target.value }))} className={fld} /></label>
              </div>
              <button onClick={rezerwuj} disabled={busy}
                className="mt-5 w-full rounded-xl bg-mint px-4 py-3 text-sm font-semibold text-bg transition hover:brightness-105 disabled:opacity-60">
                {busy ? 'Rezerwuję…' : 'Zarezerwuj stolik'}
              </button>
            </>
          )}

          {/* KROK 3 — sukces */}
          {krok === 'sukces' && wynik && (
            <div className="text-center">
              <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-mint/15 text-mint">
                <Icon name="check" className="h-7 w-7" />
              </div>
              <h2 className="font-display text-xl font-bold text-ink">
                {wynik.rezerwacja.status === 'potwierdzona' ? 'Rezerwacja potwierdzona!' : 'Rezerwacja przyjęta!'}
              </h2>
              <p className="mt-2 text-sm text-muted">
                {wynik.rezerwacja.nazwisko} · <span className="capitalize">{dataLabel}</span>, godz. {wynik.rezerwacja.godz_od}
                {wynik.rezerwacja.stolik ? ` · stolik ${wynik.rezerwacja.stolik}` : ''} · {wynik.rezerwacja.liczba_osob} os.
              </p>
              {wynik.rezerwacja.status === 'rezerwacja' && (
                <p className="mt-1 text-xs text-muted">Lokal potwierdzi rezerwację. {form.email ? 'Szczegóły wyślemy e-mailem.' : ''}</p>
              )}
              {wynik.rezerwacja.status === 'odwolana' ? (
                <div className="mt-5 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">Rezerwacja odwołana.</div>
              ) : (
                <button onClick={odwolaj} className="mt-5 w-full rounded-xl border border-line px-4 py-3 text-sm font-semibold text-muted transition hover:text-ink">
                  Odwołaj rezerwację
                </button>
              )}
              <button onClick={() => { setKrok('wybor'); setWynik(null); setSloty(null); setForm({ nazwisko: '', telefon: '', email: '', notatka: '' }) }}
                className="mt-2 w-full rounded-xl px-4 py-2 text-xs font-semibold text-muted hover:text-ink">
                Nowa rezerwacja
              </button>
            </div>
          )}
        </div>
        <p className="mt-4 text-center text-xs text-muted/60">{nazwa_lokalu} · rezerwacje online</p>
      </div>
    </div>
  )
}
