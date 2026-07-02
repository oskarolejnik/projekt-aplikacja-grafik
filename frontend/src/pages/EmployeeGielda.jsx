import { useEffect, useState, useCallback } from 'react'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'
import { Icon } from '../lib/icons'
import { api } from '../lib/api'
import { useToast } from '../components/ui/Toast'
import { NAZWY_DNI, ddmmyyyy } from '../lib/format'

// Zakładka pracownika „Giełda": wystaw swoją zmianę, przejmij cudzą, śledź swoje oferty.
const STATUS_L = {
  otwarta: 'Otwarta', zajeta: 'Czeka na managera', zaakceptowana: 'Zaakceptowana', anulowana: 'Anulowana',
}
const STATUS_KLASA = {
  otwarta: 'bg-white/10 text-muted', zajeta: 'bg-amber-400/15 text-amber-300',
  zaakceptowana: 'bg-mint/15 text-mint', anulowana: 'bg-white/10 text-muted',
}

const dzien = (iso) => `${NAZWY_DNI[new Date(iso).getDay()]} ${ddmmyyyy(iso)}`

function Zmiana({ p }) {
  return (
    <div className="min-w-0">
      <div className="font-semibold text-ink">{dzien(p.data)}{p.godz_od ? ` · ${p.godz_od}` : ''}</div>
      <div className="text-xs text-muted">{p.stanowisko}{p.rewir ? ` · ${p.rewir}` : ''}</div>
    </div>
  )
}

export default function EmployeeGielda() {
  const { toast } = useToast()
  const [oferty, setOferty] = useState(null)
  const [przydzialy, setPrzydzialy] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [o, p] = await Promise.all([api('/me/gielda/oferty'), api('/me/gielda/przydzialy')])
      setOferty(o); setPrzydzialy(p)
    } catch (e) { toast(e.message, 'error') } finally { setLoading(false) }
  }, [toast])
  useEffect(() => { load() }, [load])

  const akcja = async (fn, komunikat) => {
    setBusy(true)
    try { await fn(); toast(komunikat, 'success'); await load() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  const wystaw = (przydzial_id) => akcja(
    () => api('/me/gielda/oferty', 'POST', { przydzial_id }), 'Zmiana wystawiona na giełdzie.')
  const przejmij = (id) => akcja(
    () => api(`/me/gielda/oferty/${id}/przejmij`, 'POST'), 'Zgłoszono chęć przejęcia — czeka na managera.')
  const anuluj = (id) => akcja(
    () => api(`/me/gielda/oferty/${id}/anuluj`, 'POST'), 'Oferta anulowana.')

  if (loading) {
    return <div className="grid place-items-center py-16"><Spinner className="h-6 w-6 text-muted" /></div>
  }

  const doWystawienia = przydzialy.filter((p) => !p.wystawiony)
  const dostepne = oferty?.dostepne || []
  const moje = oferty?.moje || []

  return (
    <div className="space-y-6">
      {/* Wystaw swoją zmianę */}
      <Card className="p-4 sm:p-5">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
          <Icon name="calendar" className="h-4 w-4" /> Oddaj swoją zmianę
        </div>
        {doWystawienia.length === 0 ? (
          <p className="text-sm text-muted">Brak przyszłych zmian do wystawienia.</p>
        ) : (
          <div className="space-y-2">
            {doWystawienia.map((p) => (
              <div key={p.przydzial_id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.03] px-3 py-2.5">
                <Zmiana p={p} />
                <button onClick={() => wystaw(p.przydzial_id)} disabled={busy}
                        className="shrink-0 rounded-lg bg-mint px-3 py-1.5 text-sm font-semibold text-bg transition active:scale-[0.98] disabled:opacity-50">
                  Wystaw
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Dostępne do przejęcia */}
      <Card className="p-4 sm:p-5">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
          <Icon name="users" className="h-4 w-4" /> Dostępne zmiany kolegów
        </div>
        {dostepne.length === 0 ? (
          <p className="text-sm text-muted">Nikt teraz nie oddaje zmiany, na którą masz kwalifikację.</p>
        ) : (
          <div className="space-y-2">
            {dostepne.map((o) => (
              <div key={o.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.03] px-3 py-2.5">
                <div className="min-w-0">
                  <Zmiana p={o} />
                  <div className="mt-0.5 text-xs text-muted">Oddaje: {o.wystawiajacy}{o.powod ? ` — „${o.powod}”` : ''}</div>
                </div>
                <button onClick={() => przejmij(o.id)} disabled={busy}
                        className="shrink-0 rounded-lg bg-mint px-3 py-1.5 text-sm font-semibold text-bg transition active:scale-[0.98] disabled:opacity-50">
                  Przejmij
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Moje oferty */}
      <Card className="p-4 sm:p-5">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted">
          <Icon name="clipboard" className="h-4 w-4" /> Moje wystawione zmiany
        </div>
        {moje.length === 0 ? (
          <p className="text-sm text-muted">Nie masz wystawionych zmian.</p>
        ) : (
          <div className="space-y-2">
            {moje.map((o) => (
              <div key={o.id} className="flex items-center justify-between gap-3 rounded-xl border border-line bg-white/[0.03] px-3 py-2.5">
                <div className="min-w-0">
                  <Zmiana p={o} />
                  {o.przejmujacy && <div className="mt-0.5 text-xs text-muted">Przejmuje: {o.przejmujacy}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_KLASA[o.status] || ''}`}>{STATUS_L[o.status] || o.status}</span>
                  {(o.status === 'otwarta' || o.status === 'zajeta') && (
                    <button onClick={() => anuluj(o.id)} disabled={busy}
                            className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted transition hover:text-ink disabled:opacity-50">
                      Anuluj
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
