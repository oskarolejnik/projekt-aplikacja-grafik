import { useEffect, useState, useCallback } from 'react'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { Logo } from '../components/Logo'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'

// Portal klienta imprezy (publiczny, tokenowy — /?impreza=TOKEN). Para młoda / organizator:
// widzi kartę swojej imprezy, aktualizuje liczbę gości, pisze w wątku ustaleń, śledzi wpłaty.
// Koniec telefonów „to ile w końcu osób?" — wszystko z pisemnym śladem.

const zl = (n) => (Number(n) || 0).toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' zł'
const STATUS_LABEL = { rezerwacja: 'Rezerwacja', potwierdzona: 'Potwierdzona', odbyla: 'Odbyła się', odwolana: 'Odwołana', no_show: 'Nieodbyta' }
const AUTOR_LABEL = { klient: 'Ty', lokal: 'Lokal', system: 'Aktualizacja' }

const dataPL = (iso) => new Date(iso + 'T12:00:00').toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

export default function PortalImprezy() {
  const { toast } = useToast()
  const token = new URLSearchParams(window.location.search).get('impreza')
  const [dane, setDane] = useState(null)
  const [blad, setBlad] = useState(null)
  const [goscie, setGoscie] = useState('')
  const [wiadomosc, setWiadomosc] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const d = await api(`/online/imprezy/${token}`)
      setDane(d)
      setGoscie(d.termin.liczba_osob ?? '')
    } catch (err) {
      setBlad(err.message)
    }
  }, [token])

  useEffect(() => { load() }, [load])

  const zapiszGoscie = async () => {
    const n = parseInt(goscie, 10)
    if (!n || n < 1) { toast('Podaj liczbę gości.', 'error'); return }
    setBusy(true)
    try {
      await api(`/online/imprezy/${token}/goscie`, 'PUT', { liczba_osob: n })
      toast('Zaktualizowano liczbę gości — lokal widzi zmianę od razu.', 'success')
      await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const wyslij = async () => {
    if (!wiadomosc.trim()) return
    setBusy(true)
    try {
      await api(`/online/imprezy/${token}/wiadomosci`, 'POST', { tresc: wiadomosc.trim() })
      setWiadomosc('')
      await load()
    } catch (err) {
      toast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  if (blad) {
    return (
      <div className="grid min-h-dvh place-items-center bg-bg p-4">
        <div className="card w-full max-w-md p-8 text-center">
          <Logo className="mx-auto h-10" />
          <h1 className="mt-4 font-display text-lg font-semibold text-ink">Link nieaktualny</h1>
          <p className="mt-2 text-sm text-muted">{blad} Skontaktuj się z lokalem po nowy link do portalu.</p>
        </div>
      </div>
    )
  }
  if (!dane) {
    return <div className="grid min-h-dvh place-items-center bg-bg"><Spinner className="h-7 w-7 text-muted" /></div>
  }

  const t = dane.termin
  const wplacone = (t.zadatek || 0) + (t.zadatek_kp || 0)
  const fld = 'rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink outline-none transition placeholder:text-muted/50 focus:border-mint/60 focus:ring-2 focus:ring-mint/20'

  return (
    <div className="min-h-dvh bg-bg px-4 py-8">
      <div className="mx-auto w-full max-w-2xl space-y-5">
        <header className="flex items-center gap-3">
          <Logo className="h-9" />
          <div>
            <h1 className="font-display text-xl font-semibold tracking-tight text-ink">{dane.lokal}</h1>
            <p className="text-xs text-muted">Portal Twojej imprezy</p>
          </div>
        </header>

        <div className="card p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-display text-lg font-semibold text-ink">
                {t.typ ? t.typ.charAt(0).toUpperCase() + t.typ.slice(1) : 'Impreza'} · {t.nazwisko}
              </h2>
              <p className="mt-1 text-sm text-muted">{dataPL(t.data)}{t.sala ? ` · sala: ${t.sala}` : ''}</p>
            </div>
            <span className="rounded-full bg-white/[0.06] px-3 py-1.5 text-xs font-semibold text-ink">
              {STATUS_LABEL[t.status] || t.status}
            </span>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-line bg-white/[0.02] p-4">
              <div className="field-label">Liczba gości</div>
              {t.edycja_gosci ? (
                <div className="mt-2 flex items-center gap-2">
                  <input type="number" min="1" value={goscie} onChange={(e) => setGoscie(e.target.value)}
                         className={`${fld} w-28`} aria-label="Liczba gości" />
                  <button onClick={zapiszGoscie} disabled={busy}
                          className="rounded-xl bg-mint px-4 py-2.5 text-sm font-semibold text-bg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-50">
                    Zapisz
                  </button>
                </div>
              ) : (
                <div className="mt-2 text-2xl font-semibold tabular-nums text-ink">{t.liczba_osob ?? '—'}</div>
              )}
              <p className="mt-2 text-xs text-muted">Zmiana od razu trafia do lokalu i planowania obsady.</p>
            </div>
            <div className="rounded-xl border border-line bg-white/[0.02] p-4">
              <div className="field-label">Wpłacone dotychczas</div>
              <div className="mt-2 text-2xl font-semibold tabular-nums text-ink">{zl(wplacone)}</div>
              <p className="mt-2 text-xs text-muted">
                {t.zadatek_kp > 0 ? `w tym zadatki kasowe: ${zl(t.zadatek_kp)}` : 'zadatek zaksięgowany przez lokal'}
              </p>
            </div>
          </div>
        </div>

        {dane.oferty_menu?.length > 0 && (
          <div className="card p-6">
            <h3 className="font-display text-base font-semibold text-ink">Menu</h3>
            <p className="mt-1 text-xs text-muted">Wybierz wariant — lokal zobaczy Twój wybór od razu.</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {dane.oferty_menu.map((o) => {
                const wybrane = dane.menu_oferta_id === o.id
                return (
                  <button
                    key={o.id}
                    type="button"
                    disabled={!t.edycja_gosci || busy}
                    onClick={async () => {
                      setBusy(true)
                      try {
                        await api(`/online/imprezy/${token}/menu`, 'POST', { oferta_id: o.id })
                        toast(`Wybrano: ${o.nazwa}.`, 'success')
                        await load()
                      } catch (err) { toast(err.message, 'error') } finally { setBusy(false) }
                    }}
                    className={`rounded-xl border p-4 text-left transition active:scale-[0.99] ${
                      wybrane ? 'border-mint/60 bg-mint/[0.10]' : 'border-line bg-white/[0.02] hover:bg-white/[0.05]'
                    } disabled:cursor-not-allowed disabled:opacity-60`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-semibold text-ink">{o.nazwa}</span>
                      {wybrane && <Icon name="check" className="h-4 w-4 shrink-0 text-mint" />}
                    </div>
                    {o.opis && <p className="mt-1 text-xs leading-relaxed text-muted">{o.opis}</p>}
                    <p className="mt-2 text-sm font-semibold tabular-nums text-ink">{zl(o.cena_od_osoby)} <span className="font-normal text-muted">/ os.</span></p>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {dane.raty?.length > 0 && (
          <div className="card p-6">
            <h3 className="font-display text-base font-semibold text-ink">Harmonogram wpłat</h3>
            <div className="mt-3">
              {dane.raty.map((r) => {
                const poTerminie = !r.zaplacona && r.termin_platnosci && r.termin_platnosci < new Date().toISOString().slice(0, 10)
                return (
                  <div key={r.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line py-3 last:border-b-0">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-ink">{r.nazwa}</div>
                      {r.termin_platnosci && <div className="text-xs text-muted">do {r.termin_platnosci}</div>}
                    </div>
                    <span className="text-sm font-semibold tabular-nums text-ink">{zl(r.kwota)}</span>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                      r.zaplacona ? 'bg-success/15 text-success'
                      : poTerminie ? 'bg-danger/15 text-danger' : 'bg-white/[0.04] text-muted'}`}>
                      {r.zaplacona ? 'zapłacona' : poTerminie ? 'po terminie' : 'oczekuje'}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="mt-3 text-xs text-muted">Wpłaty księguje lokal — status zmienia się po zaksięgowaniu.</p>
          </div>
        )}

        <div className="card p-6">
          <h3 className="font-display text-base font-semibold text-ink">Ustalenia</h3>
          <p className="mt-1 text-xs text-muted">Wszystko na piśmie — bez telefonów i „kto co obiecał".</p>

          <div className="mt-4 space-y-3">
            {dane.wiadomosci.length === 0 && (
              <p className="py-4 text-center text-sm text-muted">Brak wiadomości — napisz pierwszą poniżej.</p>
            )}
            {dane.wiadomosci.map((w) => (
              <div key={w.id}
                   className={`rounded-xl px-4 py-3 text-sm ${
                     w.autor === 'klient' ? 'ml-8 bg-mint/[0.12] text-ink'
                     : w.autor === 'lokal' ? 'mr-8 border border-line bg-white/[0.03] text-ink'
                     : 'bg-transparent text-center text-xs text-muted'}`}>
                {w.autor !== 'system' && (
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                    {AUTOR_LABEL[w.autor] || w.autor}
                    {w.utworzono_at && <span className="ml-2 font-normal normal-case">{new Date(w.utworzono_at).toLocaleString('pl-PL')}</span>}
                  </div>
                )}
                {w.tresc}
              </div>
            ))}
          </div>

          <div className="mt-4 flex gap-2">
            <input
              value={wiadomosc}
              onChange={(e) => setWiadomosc(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && wyslij()}
              placeholder="Napisz do lokalu (menu, dekoracje, godziny…)"
              className={`${fld} w-full min-w-0 flex-1`}
            />
            <button onClick={wyslij} disabled={busy || !wiadomosc.trim()}
                    className="shrink-0 rounded-xl bg-cream px-4 py-2.5 text-sm font-semibold text-bg transition hover:bg-white active:scale-[0.98] disabled:opacity-50"
                    aria-label="Wyślij wiadomość">
              <Icon name="upload" className="h-4 w-4 rotate-90" />
            </button>
          </div>
        </div>

        <p className="pb-4 text-center text-xs text-muted/60">{dane.lokal} · portal klienta imprezy</p>
      </div>
    </div>
  )
}
