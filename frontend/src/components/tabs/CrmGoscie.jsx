import { useCallback, useEffect, useRef, useState } from 'react'
import { Card, SectionHeader } from '../ui/Card'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Spinner'
import { Icon } from '../../lib/icons'
import { api } from '../../lib/api'
import { subscribeReservationPrivacyPurge } from '../../lib/reservationPrivacy'
import GuestProfileDialog from './GuestProfileDialog'

// CRM gości — historia rezerwacji, scoring no-show, VIP + trwały profil 360 (tagi/alergie/preferencje).
// Lista zwraca nieosobowy `profil_ref`; karta gościa rozwiązuje profil wyłącznie po rezerwacji.
const RYZYKO = {
  wysokie: 'bg-danger/15 text-danger',
  srednie: 'bg-lemon/15 text-lemon',
  niskie: 'bg-white/10 text-muted',
}
export default function CrmGoscie() {
  const [goscie, setGoscie] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState(null)
  const [modal, setModal] = useState(null)
  const profileTriggerRef = useRef(null)
  const loadControllerRef = useRef(null)
  const loadGenerationRef = useRef(0)

  const load = useCallback(async ({ background = false } = {}) => {
    loadControllerRef.current?.abort()
    const controller = new AbortController()
    const generation = loadGenerationRef.current + 1
    loadControllerRef.current = controller
    loadGenerationRef.current = generation
    if (background) setRefreshing(true)
    else setLoading(true)
    setLoadError(null)
    try {
      const nextGuests = await api('/crm/goscie', 'GET', null, { signal: controller.signal })
      if (controller.signal.aborted || loadGenerationRef.current !== generation) return
      setGoscie(nextGuests)
    } catch (error) {
      if (controller.signal.aborted || loadGenerationRef.current !== generation || error?.name === 'AbortError') return
      setLoadError(error.message || 'Nie udało się wczytać bazy gości.')
    } finally {
      if (loadGenerationRef.current !== generation) return
      loadControllerRef.current = null
      if (background) setRefreshing(false)
      else setLoading(false)
    }
  }, [])
  useEffect(() => {
    load()
    return () => {
      loadGenerationRef.current += 1
      loadControllerRef.current?.abort()
      loadControllerRef.current = null
    }
  }, [load])

  useEffect(() => subscribeReservationPrivacyPurge(() => {
    loadGenerationRef.current += 1
    loadControllerRef.current?.abort()
    loadControllerRef.current = null
    setGoscie(null)
    setModal(null)
    setLoading(false)
    setRefreshing(false)
    setLoadError(null)
    profileTriggerRef.current = null
  }), [])

  return (
    <Card className="p-6 sm:p-8">
      <SectionHeader title="Goście (CRM)" subtitle="Historia rezerwacji, ryzyko no-show, VIP i profil 360 — otwórz kartę wybranego gościa.">
        <span className="inline-flex min-h-5 items-center gap-2 text-xs text-muted" role="status" aria-live="polite">
          {refreshing ? <><Spinner className="h-3.5 w-3.5 motion-reduce:animate-none" /> Aktualizuję…</> : null}
        </span>
      </SectionHeader>

      {loadError ? (
        <div role="alert" className="mb-4">
          <Banner variant="danger">
            <div className="flex flex-wrap items-center gap-3">
              <span>{loadError}</span>
              <Button variant="ghost" size="sm" onClick={() => load({ background: Boolean(goscie) })}>Ponów</Button>
            </div>
          </Banner>
        </div>
      ) : null}

      {loading && !goscie ? <CrmSkeleton /> : loadError && !goscie ? null : !goscie || goscie.length === 0 ? (
        <div className="mt-6 rounded-xl border border-line bg-surface-2 p-8 text-center text-sm text-muted">
          Brak danych gości — pojawią się po pierwszych rezerwacjach stolików.
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2 pr-3 font-semibold">Gość</th>
                <th className="py-2 pr-3 font-semibold">Kontakt</th>
                <th className="py-2 pr-3 text-right font-semibold">Wizyt</th>
                <th className="py-2 pr-3 text-right font-semibold">No-show</th>
                <th className="py-2 pr-3 font-semibold">Ryzyko</th>
                <th className="py-2 pr-3 font-semibold">Ostatnia</th>
              </tr>
            </thead>
            <tbody>
              {goscie.map((g) => (
                <tr key={g.profil_ref} className="border-b border-line/60 transition hover:bg-white/[0.02]">
                  <td className="py-2.5 pr-3">
                    <button
                      type="button"
                      onClick={(event) => {
                        profileTriggerRef.current = event.currentTarget
                        setModal({ reservationId: g.profil_ref })
                      }}
                      className="-my-2 inline-flex min-h-11 items-center rounded-lg py-2 text-left font-semibold text-ink transition hover:text-mint"
                      aria-label={`Otwórz kartę gościa: ${g.nazwisko || 'bez nazwiska'}`}
                    >
                      {g.nazwisko || '—'}
                    </button>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {g.vip && <Pill kol="bg-mint px-2 text-bg">VIP</Pill>}
                      {g.ma_alergie && <Pill kol="bg-danger/15 text-danger"><Icon name="warning" className="mr-0.5 inline h-3 w-3" />alergie</Pill>}
                      {(g.tagi || []).map((t) => <Pill key={t} kol="bg-white/[0.06] text-muted">{t}</Pill>)}
                    </div>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.telefon || g.email || '—'}</td>
                  <td className="py-2.5 pr-3 text-right text-ink tabular-nums">{g.wizyt} <span className="text-muted">({g.odbyte} odb.)</span></td>
                  <td className="py-2.5 pr-3 text-right text-ink tabular-nums">
                    {g.no_show}{g.no_show > 0 && <span className="text-muted"> ({g.no_show_proc}%)</span>}
                  </td>
                  <td className="py-2.5 pr-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${RYZYKO[g.ryzyko] || RYZYKO.niskie}`}>{g.ryzyko}</span>
                  </td>
                  <td className="py-2.5 pr-3 text-muted">{g.ostatnia_data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal ? (
        <GuestProfileDialog
          reservationId={modal.reservationId}
          onClose={() => setModal(null)}
          onSaved={() => load({ background: true })}
          restoreFocusRef={profileTriggerRef}
        />
      ) : null}
    </Card>
  )
}

function Pill({ children, kol }) {
  return <span className={`rounded-full py-0.5 text-[10px] font-semibold ${kol.includes('px-') ? kol : `px-1.5 ${kol}`}`}>{children}</span>
}

function CrmSkeleton() {
  return (
    <div className="space-y-2" role="status" aria-label="Ładowanie bazy gości">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex min-h-14 animate-pulse items-center gap-4 border-b border-line/60 py-2 motion-reduce:animate-none">
          <span className="h-4 w-36 rounded bg-white/[0.07]" />
          <span className="h-4 w-28 rounded bg-white/[0.05]" />
          <span className="ml-auto h-4 w-20 rounded bg-white/[0.05]" />
        </div>
      ))}
      <span className="sr-only">Ładowanie gości…</span>
    </div>
  )
}
